"""Correct glyph identities and normalize Chinese cells; keep accepted menus."""
from pathlib import Path
from collections import defaultdict
import json
import hashlib
import os
import shutil
import struct
from PIL import Image, ImageDraw, ImageFont
import build_cn3_resources as previous
import build_cn2_adapter as pack
import upstream_extract_eu_text as disc
from cn4_text_fixes import GLYPH_FIXES, TOURNAMENT

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'cn3-resources'
OUT = ROOT / 'cn4-resources'


def read(path):
    return json.loads(path.read_text('utf-8'))


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', 'utf-8')


def wide(code):
    return (0x3000 <= code <= 0x30ff or 0x3400 <= code <= 0x9fff or
            0xf900 <= code <= 0xfaff or 0xff01 <= code <= 0xff60)


def main():
    os.chdir(ROOT)
    mapping = read(BASE / 'font-identities.json')
    fixes = [{'code': c, 'before': mapping[c], 'after': text} for c, text in GLYPH_FIXES.items()]
    mapping.update(GLYPH_FIXES)
    write(OUT / 'font-identities.json', mapping)
    write(OUT / 'glyph-corrections.json', fixes)
    previous.OUT = OUT
    remapped = previous.derive_font(mapping)
    ui = read(BASE / 'game-text/translations/ui/zh-CN.json')
    changes = []
    for prefix in ('pzs3us1/00450/1/19/', 'pzs3us1/00450/2/33/'):
        for index, text in TOURNAMENT.items():
            key = prefix + str(index)
            before = ui['labels'][key]['text']
            ui['labels'][key]['text'] = text
            changes.append({'id': key, 'original': ui['labels'][key]['original'], 'before': before, 'after': text})
    # Keep exact-string fallback unambiguous for every duplicate original.
    canonical = {c['original']: c['after'] for c in changes}
    for key, row in ui['labels'].items():
        if row['original'] in canonical and row['text'] != canonical[row['original']]:
            changes.append({'id': key, 'original': row['original'], 'before': row['text'], 'after': canonical[row['original']]})
            row['text'] = canonical[row['original']]
    write(OUT / 'game-text/translations/ui/zh-CN.json', ui)
    write(OUT / 'text-corrections.json', changes)

    rawmap = {int(k, 16): int(v, 16) for k, v in read(BASE / 'font-code-map.json').items()}
    originals = {}
    for i in range(1, 8):
        for code, glyph in pack.decode_font(i).items():
            originals.setdefault(code, glyph)
    extra = {new: originals[old] for old, new in rawmap.items() if old in originals}
    native = disc.sections((pack.GAME / 'gamedata/pzs3us1/00004.bin').read_bytes())
    native_codes = set()
    for data in native[:2]:
        table, count = struct.unpack_from('<II', data, 20)
        native_codes.update(struct.unpack_from('<H', data, table + 6 * i)[0] for i in range(count))
    required = {ord(c) for row in ui['labels'].values() for c in row['text']
                if ord(c) >= 32 and ord(c) not in (0xfeff, 0xa0)}
    font = ImageFont.truetype(str(OUT / 'fonts/bt3cn-rounded-bold.ttf'), 18)
    coverage = previous.font_coverage(OUT / 'fonts/bt3cn-rounded-bold.ttf')
    normalized = {}
    # Generate one full-width cell per CJK character. Measurements, layout and
    # drawing now consume the same 20-pixel advance; latin and PAD icons retain
    # their original width. The selected font still supplies the vector raster.
    for code in sorted(set(extra) | (required - native_codes)):
        identity = mapping.get(f'{code:04X}', chr(code))
        is_wide = len(identity) == 1 and wide(ord(identity)) and code in coverage
        if code in extra and not is_wide:
            continue
        assert code in coverage, f'No outline for {code:04X}'
        cell = Image.new('RGBA', (20 if is_wide else 19, 20), (128, 128, 128, 0))
        ImageDraw.Draw(cell).text((1, 0), chr(code), font=font, fill=(128, 128, 128, 252))
        assert cell.getchannel('A').getbbox() is not None or identity.isspace(), f'{code:04X}'
        extra[code] = cell
        if is_wide:
            normalized[f'{code:04X}'] = identity
    # Keep the intentionally supplied visible middle dot from CN3.
    if 0xb7 in rawmap:
        cell = Image.new('RGBA', (10, 20), (128, 128, 128, 0))
        ImageDraw.Draw(cell).text((0, -2), '·', font=font, fill=(128, 128, 128, 252))
        extra[rawmap[0xb7]] = cell
    pack.OUT = OUT
    template, addresses = pack.font_template()
    groups = defaultdict(list)
    for code, glyph in sorted(extra.items()):
        groups[glyph.info.get('gs_alpha_levels', (0, 68, 102, 126))].append((code, glyph))
    capacity = (512 // 21) ** 2
    planes = [(levels, glyphs[i:i + capacity]) for levels, glyphs in sorted(groups.items())
              for i in range(0, len(glyphs), capacity)]
    fonts = [pack.make_font(template, addresses, planes[i:i + 2]) for i in range(0, len(planes), 2)]
    assert len(fonts) <= 5
    parts = list(native)
    parts[2:7] = fonts + [b''] * (5 - len(fonts))
    result = pack.boot_archive(parts)
    assert disc.sections(result)[:2] == native[:2] and disc.sections(result)[7:] == native[7:]
    (OUT / 'mods/pzs3us1/00004.bin').write_bytes(result)
    assert required <= native_codes | extra.keys()
    write(OUT / 'normalized-cells.json', normalized)
    write(OUT / 'cn4-manifest.json', {'edition': 'r5-CN4', 'base': 'CN3',
          'glyph_corrections': fixes, 'normalized_CJK_cells': len(normalized),
          'extra_glyphs': len(extra), 'font_sheets': len(fonts), 'new_tournament_explanations': len(TOURNAMENT),
          'changed_UI_rows': len(changes), 'font_PUA_mappings': len(remapped),
          'accepted_main_menu_preserved': True, 'network_or_protocol_edits': False, 'protocol': 5})
    print('Corrected glyphs:', fixes)
    print('Normalized CJK cells:', len(normalized), '; explanatory rows:', len(changes))


if __name__ == '__main__':
    main()
