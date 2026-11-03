"""Build private Chinese text/font resources without replacing game logic.

Reuses the official C texture decoder's address map in reverse for encoding.
Original USA font members and all non-font boot members are preserved verbatim.
"""
from pathlib import Path
from collections import Counter, defaultdict
import array
import copy
import hashlib
import json
import math
import os
import re
import shutil
import struct
import subprocess
import textwrap
from PIL import Image, ImageDraw, ImageFont
import upstream_extract_eu_text as disc
from render_cn_samples import decode_font, u32
from cn2_wording import MENU, SYSTEM, normalize

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT.parent / 'Tenkaichi3Decomp-WiiLocal-r5-CN2'
GAME = Path(r'E:\PS2 yizhi\Tenkaichi3Decomp-windows-x64\Tenkaichi3Decomp')
OUT = ROOT / 'cn2-resources'
PUA = 0xe000
PROTECTED = ('notice-', 'combo-', 'timer-', 'win-counter', 'blast-stock-counter')
FONT = Path(r'C:\Windows\Fonts\simhei.ttf')


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def wrap_cn(text):
    # Keep supplemental system messages within the game's existing dialog width.
    lines, line, width = [], '', 0
    for ch in text:
        advance = 1 if ord(ch) < 128 else 2
        if ch == '\n' or width + advance > 40:
            lines.append(line.rstrip())
            line, width = '', 0
            if ch == '\n':
                continue
        line += ch
        width += advance
    if line:
        lines.append(line.rstrip())
    return '\n'.join(lines)


def boot_archive(parts):
    header = bytearray((len(parts) + 2) * 4)
    header.extend(bytes((-len(header)) % 64))
    struct.pack_into('<I', header, 0, len(parts))
    for i, part in enumerate(parts, 1):
        struct.pack_into('<I', header, i * 4, len(header))
        header.extend(part)
        header.extend(bytes((-len(header)) % 64))
    struct.pack_into('<I', header, (len(parts) + 1) * 4, len(header))
    return bytes(header)


def font_template():
    b = (ROOT / 'private-resources/cn-font-1.fnt').read_bytes()
    adapted = bytearray(b)
    tex = u32(b, 12)
    struct.pack_into('<I', adapted, 4, tex // 4)
    struct.pack_into('<II', adapted, tex, u32(b, tex) // 4, u32(b, tex + 4) // 4)
    path = OUT / 'template.texture'
    path.write_bytes(adapted)
    subprocess.run(['tools/decode_font_texture.exe', str(path.relative_to(ROOT)),
                    str((OUT / 'template.rgba').relative_to(ROOT)),
                    str((OUT / 'template.map').relative_to(ROOT))], check=True, capture_output=True)
    addresses = array.array('I')
    addresses.frombytes((OUT / 'template.map').read_bytes())
    assert len(addresses) == 512 * 512 and len(set(addresses)) == 512 * 512
    return b, addresses


def make_font(template, addresses, planes):
    # Each 4-bit texel holds two independent 2-bit coverage values, as in the ISO.
    cols = 512 // 21
    capacity = cols * cols
    assert 1 <= len(planes) <= 2 and all(len(glyphs) <= capacity for _, glyphs in planes)
    b = bytearray(template[:u32(template, 0x14)])
    tex = u32(b, 12)
    pixels, palette = u32(b, tex), u32(b, tex + 4)
    image = bytearray(512 * 512 // 2)
    records = []
    for plane, (levels, glyphs) in enumerate(planes):
        assert len(levels) == 4
        for cell, (code, glyph) in enumerate(glyphs):
            x, y = (cell % cols) * 21, (cell // cols) * 21
            w, h = glyph.size
            assert 0 <= w <= 20 and 0 <= h <= 20
            alpha = glyph.getchannel('A').tobytes()
            for gy in range(h):
                for gx in range(w):
                    value = alpha[gy * w + gx] // 2
                    index = min(range(4), key=lambda a: abs(levels[a] - value)) << (plane * 2)
                    address = addresses[(y + gy) * 512 + x + gx]
                    at, shift = address >> 3, address & 7
                    image[at] |= index << shift
            records.append((code, x | (w << 10) | (plane << 15), y | (h << 10)))
    b[pixels + 96:pixels + 96 + len(image)] = image
    # Hardware CLUT block 0/1: top-left and top-right 8x8 quadrants of a 16x16 upload.
    for plane in range(2):
        levels = planes[plane][0] if plane < len(planes) else (0, 68, 102, 126)
        for i in range(16):
            x, y = plane * 8 + (i & 7), i >> 3
            at = palette + 96 + (y * 16 + x) * 4
            b[at:at + 4] = bytes((128, 128, 128, levels[(i >> (plane * 2)) & 3]))
    table = len(b)
    for row in sorted(records):
        b.extend(struct.pack('<HHH', *row))
    struct.pack_into('<II', b, 0x14, table, len(records))
    b.extend(bytes((-len(b)) % 64))
    return bytes(b)


def main():
    os.chdir(ROOT)
    OUT.mkdir(exist_ok=True)
    glyphs = {}
    for i in range(1, 8):
        for code, glyph in decode_font(i).items():
            glyphs.setdefault(code, glyph)
    english = json.loads((GAME / 'gamedata/game-text/translations/ui/en.json').read_text(encoding='utf-8'))
    candidates = json.loads((ROOT / 'review-only/candidate.zh-CN.json').read_text(encoding='utf-8'))['labels']
    supplemental = {normalize(k): v for k, v in SYSTEM.items()}
    raw_codes, actual_codes = set(), set()
    chosen, skipped = {}, []
    counts = Counter()
    for key, entry in english['labels'].items():
        en = entry['original']
        if normalize(en) in supplemental:
            text = wrap_cn(supplemental[normalize(en)])
            actual_codes.update(ord(ch) for ch in text if ord(ch) > 127)
            chosen[key] = ('unicode', text)
            counts['supplemental_system_rows'] += 1
        elif key in candidates:
            text = candidates[key]['text']
            # Standalone in-battle announcements remain English even if in a text table.
            if re.fullmatch(r'(?:ready|fight|k\.?o\.?|perfect|success|winner|loser|ringout|time up|hits|counter|max power|boost|lock on|first attack)[! .]*', en, re.I):
                chosen[key] = ('original', en)
                counts['protected_ui_rows'] += 1
                continue
            missing = {ord(ch) for ch in text if ord(ch) > 127 and ord(ch) not in (0xa0, 0xb7) and ord(ch) not in glyphs}
            if missing or any(0x3040 <= ord(ch) <= 0x30ff for ch in text):
                skipped.append({'id': key, 'original': en, 'reason': 'missing glyph or unreviewed Japanese',
                                'codes': [hex(c) for c in sorted(missing)]})
                chosen[key] = ('original', en)
                counts['unresolved_rows'] += 1
            else:
                text = text.replace('\xa0', ' ')
                raw_codes.update(ord(ch) for ch in text if ord(ch) > 127)
                chosen[key] = ('iso', text)
                counts['iso_rows'] += 1
        else:
            chosen[key] = ('original', en)
            skipped.append({'id': key, 'original': en, 'reason': 'table lengths differ; no positional guess'})
            counts['unresolved_rows'] += 1
    from cn2_text_repairs import supplement
    repairs = supplement(english, chosen, candidates, glyphs)
    for kind, text in chosen.values():
        if kind == 'iso': raw_codes.update(ord(ch) for ch in text if ord(ch) > 127)
        elif kind == 'unicode': actual_codes.update(ord(ch) for ch in text if ord(ch) > 127)
    raw_map = {code: PUA + i for i, code in enumerate(sorted(raw_codes))}
    assert max(raw_map.values()) <= 0xf8ff
    adapted = copy.deepcopy(english)
    adapted.update(locale='zh-CN', name='简体中文（本地适配）', order=0,
                   source='CN2 private ISO-derived text plus reviewed system messages')
    for key, (kind, text) in chosen.items():
        adapted['labels'][key]['text'] = ''.join(chr(raw_map.get(ord(ch), ord(ch))) for ch in text) if kind == 'iso' else text
    write_json(OUT / 'game-text/translations/ui/zh-CN.json', adapted)
    write_json(OUT / 'game-text/translations/ui/en.json', english)
    # Real Unicode is used for human-written supplements; ISO codes stay in the PUA.
    extra_glyphs = [(new, glyphs[old]) for old, new in raw_map.items() if old in glyphs]
    font = ImageFont.truetype(str(FONT), 18)
    for code in sorted(actual_codes - {0xa0}):
        glyph = Image.new('RGBA', (19, 20), (128, 128, 128, 0))
        draw = ImageDraw.Draw(glyph)
        draw.text((0, -2), chr(code), font=font, fill=(128, 128, 128, 252), stroke_width=0)
        extra_glyphs.append((code, glyph))
    # Middle dot is a real code in the ISO too; use the USA glyph when available.
    # The ISO's dot goes through the PUA, so provide its original-looking visible dot.
    if 0xb7 in raw_map:
        dot = Image.new('RGBA', (10, 20), (128, 128, 128, 0))
        ImageDraw.Draw(dot).text((0, -2), '·', font=font, fill=(128, 128, 128, 252))
        extra_glyphs.append((raw_map[0xb7], dot))
    assert len({c for c, _ in extra_glyphs}) == len(extra_glyphs)
    template, addresses = font_template()
    # Preserve each ISO font's exact antialias levels; they differ across sheets.
    by_palette = defaultdict(list)
    for code, glyph in extra_glyphs:
        levels = glyph.info.get('gs_alpha_levels', (0, 68, 102, 126))
        by_palette[levels].append((code, glyph))
    capacity = (512 // 21) ** 2
    planes = [(levels, group[i:i + capacity]) for levels, group in sorted(by_palette.items())
              for i in range(0, len(group), capacity)]
    fonts = [make_font(template, addresses, planes[i:i + 2]) for i in range(0, len(planes), 2)]
    assert len(fonts) <= 5
    boot = (GAME / 'gamedata/pzs3us1/00004.bin').read_bytes()
    parts = disc.sections(boot)
    assert parts is not None and len(parts) == 11 and all(not p for p in parts[2:7])
    parts[2:2 + len(fonts)] = fonts
    result = boot_archive(parts)
    assert all(a == b for a, b in zip(disc.sections(boot)[:2], disc.sections(result)[:2]))
    assert disc.sections(boot)[7:] == disc.sections(result)[7:]
    path = OUT / 'mods/pzs3us1/00004.bin'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(result)
    # Artwork labels: translate menus only. No battle artwork or counters are altered.
    labels = json.loads((SOURCE / 'port/translations/labels/en.json').read_text(encoding='utf-8'))
    labels.update(locale='zh-CN', name='简体中文（本地适配）', order=0)
    untouched = []
    for key, entry in labels['labels'].items():
        if key.startswith(PROTECTED):
            untouched.append(key)
        else:
            entry['text'] = MENU.get(entry['original'], entry['original'])
    write_json(OUT / 'game-text/translations/labels/zh-CN.json', labels)
    port = json.loads((SOURCE / 'port/translations/port/en.json').read_text(encoding='utf-8'))
    port.update(locale='zh-CN', name='简体中文（本地适配）', order=0)
    port['labels']['quit/confirm']['text'] = '关闭游戏吗？\n未保存的进度将会丢失。'
    write_json(OUT / 'game-text/translations/port/zh-CN.json', port)
    (OUT / 'fonts').mkdir(exist_ok=True)
    shutil.copy2(FONT, OUT / 'fonts/simhei.ttf')
    (OUT / 'fonts/fonts.tsv').write_text('simhei.ttf\tChinese menu (SimHei)\t1\n', encoding='utf-8')
    write_json(OUT / 'font-code-map.json', {f'{code:04X}': f'{new:04X}' for code, new in raw_map.items()})
    write_json(OUT / 'unresolved-rows.json', [row for row in skipped if chosen[row['id']][0] == 'original'])
    write_json(OUT / 'text-repair-manifest.json', repairs)
    final_counts = Counter(kind for kind, text in chosen.values())
    write_json(OUT / 'manifest.json', {
        'edition': 'r5-CN2', 'counts': dict(final_counts), 'custom_iso_codes': len(raw_map),
        'supplemental_unicode_glyphs': len(actual_codes), 'extra_font_sheets': len(fonts),
        'extra_font_glyphs': len(extra_glyphs), 'original_USA_font_members_preserved': True,
        'non_font_boot_members_preserved': True, 'protected_artwork_ids': untouched,
        'source_changes': ['src/battle/col_c.c', 'src/battle/btl_seq.c',
                           'port/src/gs/menu_labels.c', 'port/src/gs/menu_labels.h',
                           'port/src/gs/menu_text.c', 'port/src/gs/ui_text_translate.c',
                           'port/src/gs/ui_text_translate.h'], 'network_protocol_changes': False,
        'boot_sha256': hashlib.sha256(result).hexdigest(),
        'menu_labels_changed': sum(v['text'] != v['original'] for v in labels['labels'].values()),
    })
    print(json.dumps(dict(final_counts), ensure_ascii=False))
    print('Extra glyphs:', len(extra_glyphs), 'font sheets:', len(fonts), 'protected artwork labels:', len(untouched))


if __name__ == '__main__':
    main()
