"""Verify the private adapter offline without touching a running game window."""
from pathlib import Path
import hashlib
import json
import os
import struct
import subprocess
from PIL import Image
import upstream_extract_eu_text as disc
from render_cn_samples import decode_font, u32

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT.parent / 'Tenkaichi3Decomp-WiiLocal-r5'
SOURCE = ROOT.parent / 'Tenkaichi3Decomp-WiiLocal-r5-CN2'
RES = ROOT / 'cn2-resources'
OUT = ROOT / 'cn2-verification'
OUT.mkdir(exist_ok=True)


def decode_extra(data, index):
    tex = u32(data, 12)
    table, count = u32(data, 20), u32(data, 24)
    rows = [struct.unpack_from('<HHH', data, table + 6 * i) for i in range(count)]
    assert [code for code, _, _ in rows] == sorted({code for code, _, _ in rows})
    sheets = {}
    for plane in (0, 1):
        d = bytearray(data)
        palette = u32(d, tex + 4)
        colors = bytearray()
        for i in range(16):
            x, y = plane * 8 + (i & 7), i >> 3
            at = palette + 96 + (y * 16 + x) * 4
            colors.extend(d[at:at + 4])
        new = len(d)
        d.extend(bytes(96) + colors)
        struct.pack_into('<I', d, 4, tex // 4)
        struct.pack_into('<II', d, tex, u32(d, tex) // 4, new // 4)
        path = OUT / f'extra-{index}-{plane}.texture'
        path.write_bytes(d)
        rgba = path.with_suffix('.rgba')
        subprocess.run(['tools/decode_font_texture.exe', str(path.relative_to(ROOT)), str(rgba.relative_to(ROOT))],
                       check=True, capture_output=True)
        image = Image.frombytes('RGBA', (512, 512), rgba.read_bytes())
        image.putalpha(image.getchannel('A').point(lambda a: min(255, a * 2)))
        sheets[plane] = image
    result = {}
    for code, u, v in rows:
        x, y, w, h = u & 1023, v & 1023, (u >> 10) & 31, (v >> 10) & 31
        assert x + w <= 512 and y + h <= 512
        plane = (u >> 15) | ((v >> 15) << 1)
        result[code] = sheets[plane].crop((x, y, x + w, y + h))
    return result


def main():
    os.chdir(ROOT)
    originals = {}
    for i in range(1, 8):
        for code, glyph in decode_font(i).items():
            originals.setdefault(code, glyph)
    boot = disc.sections((RES / 'mods/pzs3us1/00004.bin').read_bytes())
    assert boot is not None and len(boot) == 11
    extra = {}
    for i, data in enumerate(boot[2:7], 2):
        if data:
            extra.update(decode_extra(data, i))
    mapping = {int(a, 16): int(b, 16) for a, b in json.loads((RES / 'font-code-map.json').read_text()).items()}
    verified = 0
    for old, new in mapping.items():
        if old not in originals:
            continue
        a, b = originals[old], extra[new]
        assert a.size == b.size and a.tobytes() == b.tobytes(), f'ISO glyph changed: {old:04X} -> {new:04X}'
        verified += 1
    fonts = set(extra)
    for data in boot[:2]:
        table, count = u32(data, 20), u32(data, 24)
        fonts.update(struct.unpack_from('<H', data, table + 6 * i)[0] for i in range(count))
    catalog = json.loads((RES / 'game-text/translations/ui/zh-CN.json').read_text(encoding='utf-8'))
    missing = {}
    for key, row in catalog['labels'].items():
        codes = {ord(c) for c in row['text'] if ord(c) >= 32 and ord(c) not in (0xa0, 0xfeff) and ord(c) not in fonts}
        if codes:
            missing[key] = sorted(hex(code) for code in codes)
    assert not missing, list(missing.items())[:10]
    labels = json.loads((RES / 'game-text/translations/labels/zh-CN.json').read_text(encoding='utf-8'))['labels']
    protected = [key for key in labels if key.startswith(('notice-', 'combo-', 'timer-', 'win-counter', 'blast-stock-counter'))]
    assert all(labels[key]['original'] == labels[key]['text'] for key in protected)
    original_hashes = json.loads((ROOT / 'cn1-base-source-hashes.json').read_text(encoding='utf-8'))
    changed = []
    for row in original_hashes:
        actual = hashlib.sha256((SOURCE / row['file']).read_bytes()).hexdigest()
        if actual != row['sha256']:
            changed.append(row['file'])
    assert set(changed) == {'src/battle/col_c.c', 'src/battle/btl_seq.c', 'port/src/gs/menu_labels.c', 'port/src/gs/menu_labels.h', 'port/src/gs/menu_text.c', 'port/src/gs/ui_text_translate.c', 'port/src/gs/ui_text_translate.h'}, changed
    # All existing object files are copied, and just the font-printer object is rebuilt.
    object_changes = []
    for path in (BASE / 'port/build/obj_win64').glob('*.o'):
        other = SOURCE / 'port/build/obj_win64' / path.name
        if path.read_bytes() != other.read_bytes():
            object_changes.append(path.name)
    assert set(object_changes) == {'battle_col_c.o', 'battle_btl_seq.o', 'gs_menu_labels.o', 'gs_menu_text.o', 'gs_ui_text_translate.o'}, object_changes
    assert len((SOURCE / 'port/build/bt3.exe.mem').read_text().splitlines()) > 2
    output = {
        'ISO_glyphs_repacked_pixel_identically': verified,
        'UI_catalog_entries': len(catalog['labels']), 'unresolved_glyphs': missing,
        'protected_artwork_labels_unchanged': len(protected),
        'source_changes_against_r5': changed, 'object_changes_against_r5': object_changes,
        'network_objects_byte_identical': [p.name for p in sorted((BASE / 'port/build/obj_win64').glob('gs_net*.o'))],
        'network_protocol': 5,
        'gameplay_fingerprint': 'not yet measured in CN2 runtime',
        'visual_validation': 'Pending user screenshots; offline checks do not prove layout or text alignment.',
    }
    (OUT / 'offline-checks.json').write_text(json.dumps(output, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(output, ensure_ascii=False))


if __name__ == '__main__':
    main()
