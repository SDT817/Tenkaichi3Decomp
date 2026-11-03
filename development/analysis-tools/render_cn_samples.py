"""Private glyph proof; does not edit or run the user's game.

The original C texture decoder is used without algorithm changes. Font files
use byte offsets and upload a 16x16 CLUT; adapt those to its normal texture-file
input. Font_MakeTex0 selects CLUT blocks (256 bytes in GS memory). For a
16x16 PSMCT32 upload, blocks 0..3 occupy 8x8 quadrants. The first 16 colours
read for each PSMT4 CLUT are its top two rows of eight pixels.
"""
from pathlib import Path
import json
import os
import struct
import subprocess
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
os.environ['PATH'] = r'E:\BT3-Wii-tools\mingw64\bin;' + os.environ['PATH']
OUT = ROOT / 'glyph-proof'
OUT.mkdir(exist_ok=True)


def u32(b, at):
    return struct.unpack_from('<I', b, at)[0]


def decode_font(number):
    b = (ROOT / f'private-resources/cn-font-{number}.fnt').read_bytes()
    table, count = u32(b, 0x14), u32(b, 0x18)
    glyphs = [struct.unpack_from('<HHH', b, table + 6 * i) for i in range(count)]
    planes = sorted({(u >> 15) | ((v >> 15) << 1) for _, u, v in glyphs})
    sheets = {}
    for plane in planes:
        d = bytearray(b)
        tex = u32(d, 0x0c)
        pixels, palette = u32(d, tex), u32(d, tex + 4)
        assert u32(d, palette + 0x30) == 16 and u32(d, palette + 0x34) == 16
        assert ((u32(d, tex + 0x1c) >> 8) & 63) == 0
        linear = bytearray()
        for i in range(16):
            x = (plane & 1) * 8 + (i & 7)
            y = (plane >> 1) * 8 + (i >> 3)
            at = palette + 96 + (y * 16 + x) * 4
            linear.extend(d[at:at + 4])
        appended = len(d)
        assert appended % 4 == 0
        d.extend(bytes(96) + linear)
        struct.pack_into('<I', d, 4, tex // 4)
        struct.pack_into('<II', d, tex, pixels // 4, appended // 4)
        adapted = OUT / f'font-{number}-plane-{plane}.texture'
        rgba = OUT / f'font-{number}-plane-{plane}.rgba'
        adapted.write_bytes(d)
        result = subprocess.run(['tools/decode_font_texture.exe', str(adapted.relative_to(ROOT)),
                                 str(rgba.relative_to(ROOT))], check=True, capture_output=True, text=True)
        width, height = map(int, result.stdout.split())
        image = Image.frombytes('RGBA', (width, height), rgba.read_bytes())
        image.putalpha(image.getchannel('A').point(lambda a: min(255, a * 2)))
        image.save(OUT / f'font-{number}-plane-{plane}.png')
        sheets[plane] = image
    result = {}
    for code, u, v in glyphs:
        x, y, width, height = u & 1023, v & 1023, (u >> 10) & 31, (v >> 10) & 31
        plane = (u >> 15) | ((v >> 15) << 1)
        result[code] = sheets[plane].crop((x, y, x + width, y + height))
        palette = u32(b, u32(b, 0x0c) + 4)
        levels = set()
        for i in range(16):
            px, py = (plane & 1) * 8 + (i & 7), (plane >> 1) * 8 + (i >> 3)
            levels.add(b[palette + 96 + (py * 16 + px) * 4 + 3])
        result[code].info['gs_alpha_levels'] = tuple(sorted(levels))
    return result


def render_line(text, glyphs):
    lines = text.split('\n')
    width = max(sum(glyphs[ord(ch)].width if ord(ch) in glyphs else 20 for ch in line) for line in lines)
    image = Image.new('RGBA', (max(1, width), max(1, len(lines) * 23)), (0, 0, 0, 0))
    missing = set()
    for row, line in enumerate(lines):
        x = 0
        for ch in line:
            code = 32 if ord(ch) == 0xa0 else ord(ch)
            glyph = glyphs.get(code)
            if glyph is None:
                missing.add(hex(ord(ch)))
                x += 20
            else:
                image.alpha_composite(glyph, (x, row * 23))
                x += glyph.width
    return image, sorted(missing)


def main():
    glyphs = {}
    for i in range(1, 8):
        for code, glyph in decode_font(i).items():
            glyphs.setdefault(code, glyph)
    jp = json.loads((ROOT / 'jp-text-raw.json').read_text(encoding='utf-8'))
    en = json.loads((ROOT / 'us-text-scan.json').read_text(encoding='utf-8'))
    samples = [(key, key, en[key], jp[key]) for key in en
               if key.startswith('pzs3us1/00005/') and key in jp][:14]
    # Structurally paired longer text, without claiming reviewed translation.
    for key, english in en.items():
        bits = key.split('/')
        index = int(bits[1])
        bits[1] = f'{index - 1:05d}'
        other = '/'.join(bits)
        if (index >= 448 and other in jp and 45 <= len(english) <= 130
                and '<' not in english and len(jp[other]) <= 100 and english.count('\n') <= 3):
            samples.append((key, other, english, jp[other]))
            if len(samples) == 20:
                break
    label = ImageFont.truetype(r'C:\Windows\Fonts\arial.ttf', 18)
    title = ImageFont.truetype(r'C:\Windows\Fonts\arial.ttf', 23)
    rows = []
    evidence = []
    for us_id, jp_id, english, raw in samples:
        image, missing = render_line(raw, glyphs)
        large = image.resize((image.width * 2, image.height * 2), Image.Resampling.NEAREST)
        row = Image.new('RGB', (1400, max(70, large.height + 12)), '#202733')
        draw = ImageDraw.Draw(row)
        draw.multiline_text((16, 12), english, font=label, fill='white', spacing=4)
        row.paste(large, (620, 6), large)
        rows.append(row)
        evidence.append({'us_id': us_id, 'jp_id': jp_id, 'english': english,
                         'raw_encoded_text': raw, 'missing_glyphs': missing})
    sheet = Image.new('RGB', (1400, 100 + sum(row.height + 4 for row in rows)), '#121721')
    draw = ImageDraw.Draw(sheet)
    draw.text((16, 14), 'USA text / Chinese ISO glyphs (offline resource rendering)', font=title, fill='white')
    draw.text((16, 56), 'Glyphs extracted from your ISO. This is not a screenshot of the PC port.', font=label, fill='#c4ccd7')
    y = 100
    for row in rows:
        sheet.paste(row, (0, y))
        y += row.height + 4
    sheet.save(OUT / 'cn-text-samples.png')
    sheet.crop((0, 0, 1400, 100 + sum(row.height + 4 for row in rows[:6]))).save(OUT / 'cn-text-preview.png')
    (OUT / 'samples.json').write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('Rendered', len(samples), 'samples; missing:', [r['missing_glyphs'] for r in evidence if r['missing_glyphs']])


if __name__ == '__main__':
    main()
