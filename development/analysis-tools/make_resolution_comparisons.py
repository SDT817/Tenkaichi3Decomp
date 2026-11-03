"""Five private, offline CN2 artwork comparisons; never edits or launches a game.

The inputs are decoder-exported CN2 artwork (GS alpha 128 = opaque). All three
columns have identical dimensions. The current-art column uses bilinear display
enlargement; A uses premultiplied Lanczos and mild sharpening; B separately
reconstructs outline/fill coverage at 4x. These are proposals, not captures of
the actual game renderer. Rejected pixel-art scalers are not in the comparison.
"""
from pathlib import Path
import hashlib
import json
import shutil
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from resolution_layer_enhance import enhance_layers

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'cn3-resolution-samples'
SCALE = 4
FONT = Path(r'C:\Windows\Fonts\msyh.ttc')
SAMPLES = [
    ('01-main-menu', '主菜单 · 龙珠剧情模式', 'cn449-2-5-0', (512, 256), (0, 0, 160, 32)),
    ('02-world-tournament', '主菜单选中 · 龙珠世界武道会', 'cn449-2-6-0', (512, 256), (0, 64, 160, 96)),
    ('03-heading', '栏目标题 · 主菜单', 'cn449-2-23-1', (512, 64), (0, 0, 128, 64)),
    ('04-title-choice', '标题画面 · 继续游戏', 'cn449-1-8-1', (512, 64), (200, 32, 340, 64)),
    ('05-battle-settings', '对战菜单 · 战斗设置', 'cn448-1-8-1', (512, 128), (0, 96, 160, 128)),
]
BG = '#253044'
PANEL = '#1c2637'
INK = '#edf2fa'
MUTED = '#afbed0'
COL_W = 510
GAP = 12
MARGIN = 20
WIDTH = 2 * MARGIN + 3 * COL_W + 2 * GAP


def font(size):
    return ImageFont.truetype(str(FONT), size)


def resize_premultiplied(image, size, method):
    return image.convert('RGBa').resize(size, method).convert('RGBA')


def conservative(image):
    size = image.width * SCALE, image.height * SCALE
    # Work in associated alpha to avoid dark fringes from transparent RGB.
    rgba = resize_premultiplied(image, size, Image.Resampling.LANCZOS)
    channels = rgba.convert('RGBa').split()
    channels = tuple(ch.filter(ImageFilter.UnsharpMask(radius=1.05, percent=75, threshold=3))
                     for ch in channels)
    return Image.merge('RGBa', channels).convert('RGBA')


def read_crop(name, dimensions, box):
    path = ROOT / f'cn2-artwork-inspection/{name}.rgba'
    source = path.read_bytes()
    assert len(source) == dimensions[0] * dimensions[1] * 4
    image = Image.frombytes('RGBA', dimensions, source).crop(box)
    image.putalpha(image.getchannel('A').point(lambda alpha: min(255, alpha * 2)))
    bbox = image.getchannel('A').getbbox()
    assert bbox is not None
    # Padding is transparent and identical for all methods, preventing edge cuts.
    image = image.crop(bbox)
    padded = Image.new('RGBA', (image.width + 8, image.height + 8))
    padded.paste(image, (4, 4))
    return path, source, padded, bbox


def write_row(stem, label, images):
    row = Image.new('RGB', (WIDTH, 224), BG)
    draw = ImageDraw.Draw(row)
    draw.text((MARGIN, 7), label, font=font(20), fill=INK)
    for column, image in enumerate(images):
        x, y = MARGIN + column * (COL_W + GAP), 42
        assert image.width <= COL_W - 12
        assert image.height <= 162
        draw.rounded_rectangle((x, y, x + COL_W, 218), radius=8, fill=PANEL)
        row.paste(image, (x + (COL_W - image.width) // 2,
                          y + (176 - image.height) // 2), image)
    row.save(OUT / f'{stem}-comparison.png')
    return row


def main():
    OUT.mkdir(exist_ok=True)
    manifest = {'purpose': 'Offline visual proposals only; not installed in any game.',
                'scale': SCALE, 'alpha': 'GS alpha doubled and clamped for PNG viewing only',
                'columns': ['bilinear original display', 'premultiplied Lanczos + mild unsharp mask',
                            'native outline + per-row fill separation; bicubic contours; smoothstep coverage'],
                'samples': []}
    rows = []
    for stem, label, name, dimensions, box in SAMPLES:
        path, raw, image, bbox = read_crop(name, dimensions, box)
        size = image.width * SCALE, image.height * SCALE
        original = resize_premultiplied(image, size, Image.Resampling.BILINEAR)
        candidate_a, candidate_b = conservative(image), enhance_layers(image)
        for suffix, result in [('source', image), ('current', original),
                               ('A-conservative', candidate_a), ('B-edge', candidate_b)]:
            result.save(OUT / f'{stem}-{suffix}.png')
        rows.append(write_row(stem, label, [original, candidate_a, candidate_b]))
        manifest['samples'].append({'name': stem, 'label': label, 'source': str(path.relative_to(ROOT)),
                                    'source_sha256': hashlib.sha256(raw).hexdigest(),
                                    'texture_dimensions': dimensions, 'crop_region': box,
                                    'alpha_bbox_in_region': bbox, 'padded_source_size': image.size,
                                    'comparison_size': size})

    header, footer = 146, 65
    sheet = Image.new('RGB', (WIDTH, header + sum(row.height for row in rows) + footer), BG)
    draw = ImageDraw.Draw(sheet)
    draw.text((MARGIN, 15), '汉化字图清晰度对比 · 5 组样张', font=font(30), fill=INK)
    draw.text((MARGIN, 62), '沿用 CN2 原字形与配色；相同尺寸，放大 4 倍查看笔画。离线样张，非游戏截图。',
              font=font(19), fill=MUTED)
    for i, (title, color) in enumerate([('当前素材（常规放大）', MUTED),
                                       ('A · 保守增强', '#9fd5ff'),
                                       ('B · 轮廓重建', '#a8e6bf')]):
        draw.text((MARGIN + i * (COL_W + GAP), 111), title, font=font(22), fill=color)
    y = header
    for row in rows:
        sheet.paste(row, (0, y))
        y += row.height
    draw.text((MARGIN, y + 15), '请重点比较斜线、圆角、细笔画与字内空隙；当前游戏文件未修改。',
              font=font(19), fill=MUTED)
    sheet.save(OUT / 'five-comparisons.png')
    (OUT / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    sources = OUT / 'reproduction'
    sources.mkdir(exist_ok=True)
    for name in ('make_resolution_comparisons.py', 'resolution_preview_scale.cpp',
                 'fetch_resolution_preview_dependency.py', 'resolution_layer_enhance.py',
                 'resolution_contour_preview.py'):
        shutil.copyfile(ROOT / 'tools' / name, sources / name)
    print('Generated', len(rows), 'comparisons:', OUT / 'five-comparisons.png')


if __name__ == '__main__':
    main()
