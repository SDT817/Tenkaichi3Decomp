"""Offline font alternatives; no changes to game resources or executables.

Render real Chinese text from vector fonts at 4x (2x supersampling for raster
antialiasing), fit the original visible fill region, and draw outlines/gradients
separately. Font files retain their own OFL licences under the preview vendor/.
"""
from collections import Counter
from pathlib import Path
import hashlib
import json
import shutil
import struct
import zipfile
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from make_resolution_comparisons import read_crop, SAMPLES
from resolution_layer_enhance import enhance_layers

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'cn3-font-options'
SCALE, AA = 4, 2
TEXT = ['龙珠剧情模式', '龙珠世界武道会', '主菜单', '继续游戏', '战斗设置']
FONTS = [
    ('full-rounded', '寒蝉全圆体', OUT / 'vendor/ChillRoundF.ttf'),
    ('round-gothic-medium', '寒蝉圆黑体·中等', OUT / 'vendor/ChillRoundGothic_Medium.ttf'),
    ('round-gothic-bold', '寒蝉圆黑体·粗体', OUT / 'vendor/ChillRoundGothic_Bold.ttf'),
]
UI_FONT = Path(r'C:\Windows\Fonts\msyh.ttc')
PANEL, BG, INK, MUTED = '#1c2637', '#253044', '#edf2fa', '#afbed0'
COL_W, GAP, MARGIN = 492, 12, 20
WIDTH = MARGIN * 2 + COL_W * 4 + GAP * 3


def ui(size):
    return ImageFont.truetype(str(UI_FONT), size)


def font_coverage(path):
    """Read cmap 4/12 coverage to reject missing-character substitution."""
    data = path.read_bytes()
    count = struct.unpack_from('>H', data, 4)[0]
    tables = {data[12 + i * 16:16 + i * 16]: struct.unpack_from('>II', data, 20 + i * 16)
              for i in range(count)}
    offset, _ = tables[b'cmap']
    number = struct.unpack_from('>H', data, offset + 2)[0]
    chars = set()
    for i in range(number):
        _, _, sub = struct.unpack_from('>HHI', data, offset + 4 + i * 8)
        sub += offset
        format_ = struct.unpack_from('>H', data, sub)[0]
        if format_ == 12:
            groups = struct.unpack_from('>I', data, sub + 12)[0]
            for j in range(groups):
                start, end, gid = struct.unpack_from('>III', data, sub + 16 + j * 12)
                chars.update(range(start + (gid == 0), end + 1))
        elif format_ == 4:
            segments = struct.unpack_from('>H', data, sub + 6)[0] // 2
            ends = sub + 14
            starts = ends + 2 * segments + 2
            deltas = starts + 2 * segments
            ranges = deltas + 2 * segments
            for j in range(segments):
                end = struct.unpack_from('>H', data, ends + j * 2)[0]
                start = struct.unpack_from('>H', data, starts + j * 2)[0]
                delta = struct.unpack_from('>h', data, deltas + j * 2)[0]
                relative = struct.unpack_from('>H', data, ranges + j * 2)[0]
                for code in range(start, min(end, 0xfffe) + 1):
                    gid = (code + delta) & 0xffff if not relative else struct.unpack_from(
                        '>H', data, ranges + j * 2 + relative + (code - start) * 2)[0]
                    if gid:
                        chars.add(code)
    return chars


def check_required_characters():
    """Check actual outlines, including repertoire outside the five examples.

    CN2's private-use codes address ISO glyph pictures, not real Unicode names.
    They cannot be tested against a standard Unicode font before that separate
    mapping is reconstructed. Test all known Unicode text and GB2312 Chinese.
    """
    common = set()
    for lead in range(0xb0, 0xf8):
        for trail in range(0xa1, 0xff):
            try:
                char = bytes((lead, trail)).decode('gb2312')
            except UnicodeDecodeError:
                continue
            if '\u4e00' <= char <= '\u9fff':
                common.add(char)
    assert len(common) == 6763
    catalogs = {}
    for kind in ('labels', 'ui'):
        data = json.loads((ROOT / f'cn2-resources/game-text/translations/{kind}/zh-CN.json').read_text('utf-8'))['labels']
        catalogs[kind] = {char for row in data.values() for char in row['text']
                          if ord(char) >= 32 and not char.isspace() and ord(char) != 0xfeff
                          and not 0xe000 <= ord(char) <= 0xf8ff}
    required = common | catalogs['labels'] | catalogs['ui']
    report = {'GB2312_Chinese_characters': len(common),
              'menu_catalog_characters': len(catalogs['labels']),
              'UI_catalog_known_Unicode_characters': len(catalogs['ui']),
              'distinct_characters_checked_per_font': len(required),
              'ISO_private_use_code_mapping': 'Not standard Unicode; separate mapping work is required before vector UI-font replacement.',
              'fonts': []}
    for key, title, path in FONTS:
        cmap = font_coverage(path)
        font = ImageFont.truetype(str(path), 40)
        absent = [char for char in sorted(required) if ord(char) not in cmap]
        empty = [char for char in sorted(required) if ord(char) in cmap and font.getmask(char).getbbox() is None]
        row = {'font': key, 'name': title, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
               'missing_cmap_characters': absent, 'empty_outline_characters': empty}
        report['fonts'].append(row)
        assert not absent and not empty, row
    (OUT / 'records/full-font-coverage.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return report


def fill_geometry(source):
    """Measure a shared fill rectangle only, never derive new vector contours."""
    rgba = np.asarray(source, dtype=float)
    rgb, alpha = rgba[:, :, :3], rgba[:, :, 3]
    colors = Counter(tuple(map(int, px[:3])) for px in rgba.reshape(-1, 4) if px[3] == 255)
    outline = np.asarray(colors.most_common(1)[0][0], dtype=float)
    dist = np.linalg.norm(rgb - outline, axis=2)
    dist[alpha < 250] = 0
    cutoff = max(20, float(dist.max()) * 0.5)
    ys, xs = np.nonzero(dist >= cutoff)
    assert len(xs)
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


def vector_mask(text, path, source, sample_index):
    font = ImageFont.truetype(str(path), 240)
    def render(word):
        bbox = font.getbbox(word)
        raw = Image.new('L', (bbox[2] - bbox[0] + 32, bbox[3] - bbox[1] + 32))
        draw = ImageDraw.Draw(raw)
        draw.text((16 - bbox[0], 16 - bbox[1]), word, font=font, fill=255,
                  spacing=0, stroke_width=0)
        return raw.crop(raw.getbbox())
    left, top, right, bottom = fill_geometry(source)
    factor = SCALE * AA
    size = (source.width * factor, source.height * factor)
    mask = Image.new('L', size)
    # Keep each label's original fill bounds instead of enlarging the text.
    if sample_index == 2:
        # The native heading spaces the three characters far apart. Preserve
        # those individual slots instead of stretching the phrase over gaps.
        occupied = (np.asarray(source.getchannel('A')) > 128).any(axis=0)
        runs, start = [], None
        for x, value in enumerate(list(occupied) + [False]):
            if value and start is None:
                start = x
            elif not value and start is not None:
                runs.append((start, x))
                start = None
        assert len(runs) == len(text)
        for char, (a, b) in zip(text, runs):
            ch_bounds = fill_geometry(source.crop((a, 0, b, source.height)))
            cl, ct, cr, cb = ch_bounds
            fitted = render(char).resize(((cr - cl) * factor, (cb - ct) * factor), Image.Resampling.LANCZOS)
            mask.paste(fitted, ((a + cl) * factor, ct * factor))
    else:
        fitted = render(text).resize(((right - left) * factor, (bottom - top) * factor), Image.Resampling.LANCZOS)
        mask.paste(fitted, (left * factor, top * factor))
    stroke = 1.5 if sample_index == 2 else 1.75
    radius = max(1, round(stroke * factor))
    # Circular dilation: use a supersampled disk instead of a square MaxFilter.
    outer = np.zeros((size[1], size[0]), dtype=np.uint8)
    a = np.asarray(mask)
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            if dx * dx + dy * dy > radius * radius:
                continue
            sy, sx = max(0, -dy), max(0, -dx)
            ty, tx = max(0, dy), max(0, dx)
            height, width = size[1] - abs(dy), size[0] - abs(dx)
            np.maximum(outer[ty:ty + height, tx:tx + width],
                       a[sy:sy + height, sx:sx + width],
                       out=outer[ty:ty + height, tx:tx + width])
    mask = mask.resize((source.width * SCALE, source.height * SCALE), Image.Resampling.LANCZOS)
    border = Image.fromarray(outer, 'L').resize(mask.size, Image.Resampling.LANCZOS)
    return mask, border, (left, top, right, bottom), stroke


def paint(mask, border, bounds, index):
    if index == 0:
        color_top = color_bottom = (203, 203, 203)
        outline = (70, 0, 89)
    elif index == 2:
        color_top, color_bottom, outline = (248, 149, 51), (255, 34, 34), (255, 238, 216)
    else:
        color_top, color_bottom, outline = (244, 239, 137), (210, 104, 75), (44, 21, 27)
    _, top, _, bottom = bounds
    t = np.clip(((np.arange(mask.height) + 0.5) / SCALE - top) / max(bottom - top, 1), 0, 1)
    fill = np.asarray(color_top)[None, :] * (1 - t[:, None]) + np.asarray(color_bottom)[None, :] * t[:, None]
    base = np.empty((mask.height, mask.width, 4), dtype=np.uint8)
    base[:, :, :3] = outline
    base[:, :, 3] = np.asarray(border)
    rgba = np.empty_like(base)
    rgba[:, :, :3] = np.rint(fill)[:, None, :]
    rgba[:, :, 3] = np.asarray(mask)
    output = Image.alpha_composite(Image.fromarray(base, 'RGBA'), Image.fromarray(rgba, 'RGBA'))
    return output


def main():
    OUT.mkdir(exist_ok=True)
    (OUT / 'records').mkdir(exist_ok=True)
    full_coverage = check_required_characters()
    coverage = {key: font_coverage(path) for key, _, path in FONTS}
    missing = {key: sorted({ch for text in TEXT for ch in text if ord(ch) not in supported})
               for key, supported in coverage.items()}
    assert not any(missing.values()), missing
    # Some unfinished fonts map real code points to empty outlines. cmap alone
    # cannot detect that: validate every requested visible glyph by raster ink.
    for key, _, path in FONTS:
        font = ImageFont.truetype(str(path), 120)
        assert all(font.getmask(ch).getbbox() is not None for text in TEXT for ch in text), key
    rows, manifest = [], {'type': 'Offline vector-font proposals, not installed in the game.',
                          'scale': SCALE, 'supersample': AA, 'samples': [], 'fonts': [],
                          'full_coverage_checked_characters_per_font': full_coverage['distinct_characters_checked_per_font']}
    for key, title, path in FONTS:
        manifest['fonts'].append({'key': key, 'title': title, 'file': str(path.relative_to(OUT)),
                                  'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                                  'missing_sample_glyphs': missing[key]})
    for i, ((stem, label, name, dimensions, crop), text) in enumerate(zip(SAMPLES, TEXT)):
        source_path, raw, source, _ = read_crop(name, dimensions, crop)
        previous = enhance_layers(source)
        previous.save(OUT / f'{stem}-previous-B.png')
        images = [previous]
        geometry = []
        for key, title, path in FONTS:
            mask, border, bounds, stroke = vector_mask(text, path, source, i)
            result = paint(mask, border, bounds, i)
            assert result.size == previous.size
            result.save(OUT / f'{stem}-{key}.png')
            images.append(result)
            geometry.append({'font': key, 'source_fill_bounds': bounds, 'outline_radius_in_source_pixels': stroke})
        row = Image.new('RGB', (WIDTH, 218), BG)
        draw = ImageDraw.Draw(row)
        draw.text((MARGIN, 6), label, font=ui(20), fill=INK)
        for col, im in enumerate(images):
            x, y = MARGIN + col * (COL_W + GAP), 40
            draw.rounded_rectangle((x, y, x + COL_W, 212), radius=8, fill=PANEL)
            assert im.width <= COL_W and im.height <= 170
            row.paste(im, (x + (COL_W - im.width) // 2, y + (172 - im.height) // 2), im)
        row.save(OUT / f'{stem}-comparison.png')
        rows.append(row)
        manifest['samples'].append({'stem': stem, 'wording': text, 'source': str(source_path.relative_to(ROOT)),
                                    'source_sha256': hashlib.sha256(raw).hexdigest(),
                                    'output_size': previous.size, 'rendering': geometry})
    header, footer = 145, 60
    sheet = Image.new('RGB', (WIDTH, header + sum(row.height for row in rows) + footer), BG)
    draw = ImageDraw.Draw(sheet)
    draw.text((MARGIN, 15), '相似矢量字体方案 · 原尺寸布局，4 倍清晰度样张', font=ui(30), fill=INK)
    draw.text((MARGIN, 64), '字形独立于颜色生成，渐变与描边由程序统一绘制；离线比较，尚未替换游戏。', font=ui(20), fill=MUTED)
    for col, title in enumerate(['上一版 B · 轮廓重建'] + [title for _, title, _ in FONTS]):
        draw.text((MARGIN + col * (COL_W + GAP), 108), title, font=ui(23), fill=INK if col == 0 else '#a8e6bf')
    y = header
    for row in rows:
        sheet.paste(row, (0, y))
        y += row.height
    draw.text((MARGIN, y + 15), '字体是候选，不是原版字体鉴定结果。文字大小与占位按原贴图匹配。', font=ui(20), fill=MUTED)
    sheet.save(OUT / 'vector-font-comparisons.png')
    (OUT / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    patch = []
    for filename in ('fetch_font_preview_candidates.py', 'make_vector_font_options.py'):
        path = ROOT / 'tools' / filename
        data = path.read_text('utf-8')
        relative = path.relative_to(ROOT.parent).as_posix()
        patch.extend([f'diff --git a/{relative} b/{relative}\n', 'new file mode 100644\n',
                      '--- /dev/null\n', f'+++ b/{relative}\n', f'@@ -0,0 +1,{len(data.splitlines())} @@\n'])
        patch.extend('+' + line + '\n' for line in data.splitlines())
        shutil.copyfile(path, OUT / 'records' / filename)
    (OUT / 'records/vector-preview-tools.patch').write_text(''.join(patch), encoding='utf-8', newline='\n')
    # Keep the two already-existing dependencies with the new tool snapshot.
    for filename in ('make_resolution_comparisons.py', 'resolution_layer_enhance.py'):
        shutil.copyfile(ROOT / 'tools' / filename, OUT / 'records' / filename)
    with zipfile.ZipFile(OUT / 'records/complete-preview-source.zip', 'w', zipfile.ZIP_DEFLATED) as archive:
        for path in sorted((OUT / 'records').glob('*')):
            if path.suffix != '.zip':
                archive.write(path, 'tools/' + path.name)
        archive.write(OUT / 'manifest.json', 'manifest.json')
        active = {path.name for _, _, path in FONTS} | {'ChillRound-OFL.txt', 'ChillRoundGothic-OFL.txt', 'SOURCE.json'}
        for path in sorted((OUT / 'vendor').glob('*')):
            if path.name not in active:
                continue
            archive.write(path, 'vendor/' + path.name)
    print('Generated five rows, three vector fonts; no missing sample glyphs:', OUT / 'vector-font-comparisons.png')


if __name__ == '__main__':
    main()
