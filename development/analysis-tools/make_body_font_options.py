"""Three offline body-text comparisons, using CN2's real encoded text and glyphs.

The Unicode transcriptions are reviewed against the ISO-derived glyph pictures.
This is a partial, sample-only mapping, not an automatic decoding of the UI font.
No game files, executable, networking or protocol code are changed.
"""
from pathlib import Path
import hashlib
import json
import shutil
import zipfile

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from make_vector_font_options import FONTS, font_coverage


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'cn3-body-font-options'
RECORDS = OUT / 'records'
INPUT = RECORDS / 'input'
SCALE, AA = 4, 2
CANVAS = (350, 93)
DISPLAY = (788, 186)
LINE_HEIGHT = 23
OUTLINE_RADIUS = 0.7
FILL, OUTLINE = (228, 228, 225), (31, 38, 47)
BG, PANEL, INK, MUTED = '#202b3b', '#123c69', '#eef3fa', '#b6c5d6'
UI_FONT = Path(r'C:\Windows\Fonts\msyh.ttc')
REFERENCE = Path(r'C:\Users\Admin\AppData\Local\Temp\codex-clipboard-dd7286ff-3082-4e22-b5a7-1bf0665c10c8.png')
SAMPLES = [
    ('01-challenge-description', '第 1 组 · 挑战模式介绍（你截图中的文字）',
     'pzs3us1/00451/1/8/3',
     '为了制造最强人造人，格罗博士\n收集的…战斗程序。\n应该能帮你解解闷吧？'),
    ('02-story-description', '第 2 组 · 剧情简介（含数字）',
     'pzs3us1/00460/2/6/89',
     '格罗博士死后，他的计算机\n独自制造的人造人１３号，\n突然出现在悟空等人面前。'),
    ('03-item-description', '第 3 组 · 道具说明（含括号、标点）',
     'pzs3us1/00448/2/51/5/162',
     '＜正能量效果＞\n·【攻击、防御、气力、必杀】所有\n　能力提升。'),
]


def write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save_inputs():
    """Archive only the three text records and source planes needed for replay."""
    catalog_path = ROOT / 'cn2-resources/game-text/translations/ui/zh-CN.json'
    glyph_path = ROOT / 'resolution-workload-20261022/font-glyphs.json'
    if catalog_path.is_file() and glyph_path.is_file():
        catalog = json.loads(catalog_path.read_text('utf-8'))['labels']
        samples = {key: catalog[key] for _, _, key, _ in SAMPLES}
        codes = {ord(c) for row in samples.values() for c in row['text'] if c != '\n'}
        glyphs = [g for g in json.loads(glyph_path.read_text('utf-8'))
                  if int(g['code'], 16) in codes]
        write_json(INPUT / 'samples.json', samples)
        write_json(INPUT / 'glyphs.json', glyphs)
        for member, plane in sorted({(g['font_member'], g['plane']) for g in glyphs}):
            name = f'font-{member}-plane-{plane}.png'
            shutil.copy2(ROOT / 'resolution-workload-20261022/font-planes' / name, INPUT / name)
        write_json(INPUT / 'sources.json', {
            'catalog': str(catalog_path.relative_to(ROOT)), 'catalog_sha256': sha256(catalog_path),
            'glyph_index': str(glyph_path.relative_to(ROOT)), 'glyph_index_sha256': sha256(glyph_path),
            'planes': {p.name: sha256(p) for p in sorted(INPUT.glob('font-*.png'))},
        })
    return json.loads((INPUT / 'samples.json').read_text('utf-8'))


def load_glyphs():
    planes, result = {}, {}
    for g in json.loads((INPUT / 'glyphs.json').read_text('utf-8')):
        key = (g['font_member'], g['plane'])
        if key not in planes:
            planes[key] = Image.open(INPUT / f'font-{key[0]}-plane-{key[1]}.png').convert('RGBA')
        x, y, width, height = [g[k] for k in ('x', 'y', 'width', 'height')]
        result[int(g['code'], 16)] = planes[key].crop((x, y, x + width, y + height)).getchannel('A')
    return result


def check_transcriptions(catalog):
    mapping = {}
    for _, _, key, text in SAMPLES:
        encoded = catalog[key]['text']
        assert [len(l) for l in encoded.split('\n')] == [len(l) for l in text.split('\n')], key
        for raw, actual in zip(encoded, text):
            assert raw not in mapping or mapping[raw] == actual, (key, raw, actual)
            mapping[raw] = actual
    mapping.pop('\n')
    write_json(RECORDS / 'sample-glyph-identities.json', {
        'scope': 'Manually read from the three CN2 glyph-rendered samples only; not a complete UI code map.',
        'count': len(mapping), 'encoded_to_Unicode': {f'{ord(c):04X}': u for c, u in sorted(mapping.items())},
    })


def disk_dilate(mask, radius):
    """Reuse the circular maximum construction of make_vector_font_options.py."""
    a = np.asarray(mask)
    result = np.zeros_like(a)
    height, width = a.shape
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            if dx * dx + dy * dy > radius * radius:
                continue
            sy, sx, ty, tx = max(0, -dy), max(0, -dx), max(0, dy), max(0, dx)
            h, w = height - abs(dy), width - abs(dx)
            np.maximum(result[ty:ty+h, tx:tx+w], a[sy:sy+h, sx:sx+w],
                       out=result[ty:ty+h, tx:tx+w])
    return Image.fromarray(result)


def native_mask(encoded, glyphs):
    mask = Image.new('L', CANVAS)
    for row, line in enumerate(encoded.split('\n')):
        x = 12
        for ch in line:
            g = glyphs[ord(ch)]
            mask.paste(g, (x, 10 + row * LINE_HEIGHT))
            x += g.width
        assert x <= CANVAS[0] - 12
    # Simulate linear filtering of the existing 18/19-pixel atlas, without sharpening.
    return mask.resize(tuple(v * SCALE * AA for v in CANVAS), Image.Resampling.BILINEAR)


def vector_mask(text, encoded, glyphs, path):
    font = ImageFont.truetype(str(path), 400)
    han = {ch for _, _, _, t in SAMPLES for ch in t if '\u4e00' <= ch <= '\u9fff'}
    boxes = [font.getbbox(ch, anchor='ls') for ch in han]
    top, bottom = min(b[1] for b in boxes), max(b[3] for b in boxes)
    widest = max(b[2] - b[0] for b in boxes)
    ratio = min(18 / (bottom - top), 18 / widest)
    factor = SCALE * AA
    mask = Image.new('L', tuple(v * factor for v in CANVAS))
    for row, (line, raw_line) in enumerate(zip(text.split('\n'), encoded.split('\n'))):
        x = 12
        for ch, raw in zip(line, raw_line):
            advance = glyphs[ord(raw)].width
            if not ch.isspace():
                left, upper, right, lower = font.getbbox(ch, anchor='ls')
                glyph = Image.new('L', (right-left, lower-upper))
                ImageDraw.Draw(glyph).text((-left, -upper), ch, font=font, anchor='ls', fill=255)
                size = (max(1, round(glyph.width * ratio * factor)),
                        max(1, round(glyph.height * ratio * factor)))
                glyph = glyph.resize(size, Image.Resampling.LANCZOS)
                dx = x + (advance - font.getlength(ch) * ratio) / 2 + left * ratio
                dy = 10 + row * LINE_HEIGHT + (upper - top) * ratio
                mask.paste(glyph, (round(dx * factor), round(dy * factor)))
            x += advance
    # Match the existing atlas's 252/255 maximum opacity for every candidate.
    mask = mask.point(lambda a: (a * 252 + 127) // 255)
    return mask, {'Han_ink_height_limit': 18, 'uniform_outline_scale': ratio,
                  'native_baseline': 10 - top * ratio, 'per_glyph_stretch': False,
                  'advance_widths': 'CN2 original glyph widths, including original punctuation slots'}


def finish(mask):
    factor = SCALE * AA
    outline = disk_dilate(mask, round(OUTLINE_RADIUS * factor))
    shadow = Image.new('L', mask.size)
    shadow.paste(outline, (round(0.65 * factor), round(0.65 * factor)))
    base = Image.new('RGBA', mask.size, (0, 0, 0, 0))
    for color, alpha in (((0, 0, 0), shadow.point(lambda a: a * 120 // 255)),
                         (OUTLINE, outline), (FILL, mask)):
        layer = Image.new('RGBA', mask.size, color + (0,))
        layer.putalpha(alpha)
        base = Image.alpha_composite(base, layer)
    return base.resize(tuple(v * SCALE for v in CANVAS), Image.Resampling.LANCZOS)


def ui(size):
    return ImageFont.truetype(str(UI_FONT), size)


def comparison(stem, title, images):
    margin, gap, panel_width, panel_height, header, footer = 20, 18, 828, 258, 112, 66
    width = 2 * panel_width + gap + 2 * margin
    height = header + 2 * panel_height + gap + footer
    image = Image.new('RGB', (width, height), BG)
    draw = ImageDraw.Draw(image)
    draw.text((margin, 16), title, font=ui(30), fill=INK)
    draw.text((margin, 64), '同一段文字、原换行与字符占位；统一字色和细描边。离线字库样张。', font=ui(21), fill=MUTED)
    names = ['原字库 · 线性放大对照'] + [title for _, title, _ in FONTS]
    for i, (name, im) in enumerate(zip(names, images)):
        x, y = margin + (i % 2) * (panel_width + gap), header + (i // 2) * (panel_height + gap)
        draw.rounded_rectangle((x, y, x+panel_width, y+panel_height), radius=10, fill=PANEL)
        draw.text((x+18, y+12), name, font=ui(24), fill=INK if i == 0 else '#b5edc9')
        shown = im.resize(DISPLAY, Image.Resampling.LANCZOS)
        image.paste(shown, (x+20, y+59), shown)
    draw.text((margin, height-44), '主菜单已选：寒蝉圆黑体·粗体。这里仅比较说明文字；不代表已接入游戏。', font=ui(20), fill=MUTED)
    image.save(OUT / f'{stem}-comparison.png')
    return image


def save_code_records(manifest):
    names = ('make_body_font_options.py', 'make_vector_font_options.py',
             'make_resolution_comparisons.py', 'resolution_layer_enhance.py')
    for name in names:
        shutil.copy2(ROOT / 'tools' / name, RECORDS / name)
    path = ROOT / 'tools/make_body_font_options.py'
    text = path.read_text('utf-8')
    relative = path.relative_to(ROOT.parent).as_posix()
    patch = [f'diff --git a/{relative} b/{relative}\n', 'new file mode 100644\n',
             '--- /dev/null\n', f'+++ b/{relative}\n', f'@@ -0,0 +1,{len(text.splitlines())} @@\n']
    patch.extend('+' + line + '\n' for line in text.splitlines())
    (RECORDS / 'body-font-preview-tools.patch').write_text(''.join(patch), encoding='utf-8', newline='\n')
    write_json(RECORDS / 'tool-hashes.json', {name: sha256(RECORDS / name) for name in names})
    if REFERENCE.is_file():
        shutil.copy2(REFERENCE, RECORDS / 'user-reference.png')
        manifest['user_reference_sha256'] = sha256(REFERENCE)
    write_json(OUT / 'manifest.json', manifest)
    with zipfile.ZipFile(RECORDS / 'complete-body-preview-source.zip', 'w', zipfile.ZIP_DEFLATED) as archive:
        for name in names:
            archive.write(ROOT / 'tools' / name, 'tools/' + name)
        for p in sorted(INPUT.glob('*')):
            archive.write(p, 'cn3-body-font-options/records/input/' + p.name)
        for p in (OUT / 'manifest.json', OUT / 'README.md', RECORDS / 'sample-glyph-identities.json',
                  RECORDS / 'body-font-preview-tools.patch', RECORDS / 'tool-hashes.json',
                  ROOT / 'cn3-font-options/selection.json', ROOT / 'cn3-font-options/records/full-font-coverage.json'):
            archive.write(p, str(p.relative_to(ROOT)))
        vendor = ROOT / 'cn3-font-options/vendor'
        for name in [p.name for _, _, p in FONTS] + ['SOURCE.json', 'ChillRound-OFL.txt', 'ChillRoundGothic-OFL.txt']:
            archive.write(vendor / name, 'cn3-font-options/vendor/' + name)


def main():
    INPUT.mkdir(parents=True, exist_ok=True)
    catalog = save_inputs()
    glyphs = load_glyphs()
    check_transcriptions(catalog)
    required = {ch for _, _, _, text in SAMPLES for ch in text if not ch.isspace()}
    fonts = []
    for key, title, path in FONTS:
        coverage = font_coverage(path)
        font = ImageFont.truetype(str(path), 100)
        missing = sorted(ch for ch in required if ord(ch) not in coverage)
        empty = sorted(ch for ch in required if font.getmask(ch).getbbox() is None)
        assert not missing and not empty, (key, missing, empty)
        fonts.append({'key': key, 'name': title, 'file': path.name, 'sha256': sha256(path),
                      'checked_sample_characters': len(required), 'missing': missing, 'empty': empty})
    chosen = next(f for f in fonts if f['key'] == 'round-gothic-bold')
    selection = {'date': '2026-10-22', 'menu_art': {'font': chosen['file'], 'name': chosen['name'],
                 'sha256': chosen['sha256'], 'status': 'User selected; runtime integration pending'},
                 'body_text': {'status': 'Three sample groups awaiting user selection'},
                 'game_modified_by_this_preview': False}
    selection_path = ROOT / 'cn3-font-options/selection.json'
    if selection_path.is_file():
        # Rebuilding old comparisons must not reset subsequent user decisions.
        selection = json.loads(selection_path.read_text('utf-8'))
    else:
        write_json(selection_path, selection)
    manifest = {'date': '2026-10-22', 'type': 'Offline body-text font comparisons', 'fonts': fonts,
                'native_canvas': CANVAS, 'scale': SCALE, 'supersample': AA,
                'comparison_display_size': DISPLAY, 'line_height': LINE_HEIGHT,
                'fill_RGB': FILL, 'outline_RGB': OUTLINE, 'outline_radius': OUTLINE_RADIUS,
                'source_filter': 'linear, no sharpening', 'samples': [], 'game_modified': False,
                'network_modified': False, 'protocol_modified': False}
    panels = []
    for stem, title, key, text in SAMPLES:
        encoded = catalog[key]['text']
        masks = [('native', native_mask(encoded, glyphs), None)]
        for font_key, _, path in FONTS:
            mask, geometry = vector_mask(text, encoded, glyphs, path)
            masks.append((font_key, mask, geometry))
        images = []
        for font_key, mask, geometry in masks:
            image = finish(mask)
            assert image.size == tuple(v * SCALE for v in CANVAS)
            # Padding must contain the outline/shadow, with no clipped glyph edges.
            bbox = image.getbbox()
            assert bbox and bbox[0] > 0 and bbox[1] > 0 and bbox[2] < image.width and bbox[3] < image.height
            image.save(OUT / f'{stem}-{font_key}-4x.png')
            images.append(image)
        panels.append(comparison(stem, title, images))
        manifest['samples'].append({'id': key, 'stem': stem, 'wording': text, 'encoded': encoded,
                                    'original_English': catalog[key]['original'],
                                    'rendering': {k: geometry for k, _, geometry in masks if geometry}})
    sheet = Image.new('RGB', (panels[0].width, sum(p.height for p in panels)), BG)
    y = 0
    for panel in panels:
        sheet.paste(panel, (0, y))
        y += panel.height
    sheet.save(OUT / 'body-font-comparisons.png')
    (OUT / 'README.md').write_text(
        '# 说明文字字体对比\n\n2026-10-22。主菜单已选寒蝉圆黑体·粗体；说明文字等待选定。\n\n'
        '三个样本分别是挑战模式说明、剧情简介、道具效果，均取自现用 CN2 字库和翻译目录。'
        '先按原始编码离线排出旧字图，人工核对真实汉字，再用同一文本绘制三款矢量候选。'
        '人工对应仅覆盖这三个样本，不能当作整个游戏的 Unicode 映射。\n\n'
        '每组左上为现用字库线性放大；右上为全圆体，左下为圆黑体中等，右下为圆黑体粗体。'
        '保留原来每字前进宽度、标点占位和换行；候选统一使用 18 像素汉字轮廓限高、0.7 像素细描边、'
        '相同灰白字色。字体自身轮廓保持比例，不逐字拉伸。原字库对照没有锐化，四种共用配色及描边。'
        '输出 4 倍 RGBA，并附接近截图字高的显示样张；蓝底为统一比较底色，属于离线模拟而非实机截图。\n\n'
        '三款字体均检查样本编码覆盖及非空字形。完整字库既有的 6,873 字检查记录仍在 cn3-font-options/records。'
        '字体文件、OFL 许可与来源沿用 cn3-font-options/vendor。\n\n'
        '代码快照、新增工具补丁、样本原始输入、局部字形映射与完整源码包保存于 records。'
        '源码包可解压后执行 python tools/make_body_font_options.py 重现，需要 Pillow、NumPy 和 Windows 微软雅黑。'
        '本次不修改游戏资源或可执行文件，不运行游戏，不修改联机或协议代码。\n', encoding='utf-8')
    save_code_records(manifest)
    print('Created three groups, four variants per group; no missing or empty sample glyphs.')
    print(OUT / 'body-font-comparisons.png')


if __name__ == '__main__':
    main()
