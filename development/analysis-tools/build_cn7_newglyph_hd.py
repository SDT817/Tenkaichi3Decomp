"""Real rounded-bold previews of 184 candidate glyph identities, awaiting user review.

This builds an isolated font/sheet for the existing native renderer. It never
overwrites the reviewed font, CN7 resources, game folder or user progress.
"""
from collections import Counter, defaultdict
from pathlib import Path
import base64, hashlib, io, json, math, os, re, struct, subprocess
from PIL import Image, ImageDraw, ImageFont
import build_cn3_resources as fonts
import build_cn2_adapter as pack
import verify_cn6_resources as decode
from build_full_glyph_review import pair_picture, context_parts

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'cn7-resources'
OUT = ROOT / 'cn7-glyph-review-184-HD'
RES = OUT / 'preview-resources'
NATIVE = OUT / 'native-verification'
RECORDS = OUT / 'records'
FONT = 'fonts/bt3cn-rounded-bold.ttf'
# Pixelated originals/competing readings make these especially useful to review.
PRIORITY = {'E7A9', 'E7BE', 'E7F5', 'E7F7', 'E819', 'E81C', 'E83A', 'E852'}


def read(path):
    return json.loads(path.read_text('utf-8'))


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', 'utf-8')


def sha(b):
    return hashlib.sha256(b).hexdigest()


def main():
    os.chdir(ROOT)
    assert not (RECORDS / 'manifest.json').exists(), 'Keep finalized review editions and user progress'
    RES.mkdir(exist_ok=True)
    (RES / 'fonts').mkdir(exist_ok=True)
    NATIVE.mkdir(exist_ok=True)
    RECORDS.mkdir(exist_ok=True)
    (OUT / '对照图').mkdir(exist_ok=True)
    identities = read(BASE / 'font-identities.json')
    mapping = read(OUT / 'identification/manual-candidates.json')
    source_codes = read(BASE / 'unreviewed-new-glyph-codes.json')
    reverse = {code: raw for raw, code in source_codes.items()}
    sources = read(ROOT / 'cn7-analysis/new-glyph-sources.json')
    assert set(mapping) == set(reverse) and len(mapping) == 184
    assert not identities.keys() & mapping.keys()
    _, cmap = fonts.cmap((BASE / FONT).read_bytes())
    assert all(len(ch) == 1 and ord(ch) in cmap and ord(ch) >= 32 and not 0xe000 <= ord(ch) <= 0xf8ff
               for ch in mapping.values()), 'Every candidate must have a real rounded-bold outline'
    fonts.OUT = RES
    fonts.derive_font(identities | mapping)
    before_tables, before_cmap = fonts.cmap((BASE / FONT).read_bytes())
    data = (RES / FONT).read_bytes()
    tables, cmap = fonts.cmap(data)
    assert all(cmap[code] == glyph for code, glyph in before_cmap.items())
    assert set(cmap) - set(before_cmap) == {int(code,16) for code in mapping}
    assert all(cmap[int(code,16)] == cmap[ord(ch)] for code, ch in mapping.items())
    for tag, (offset, size) in before_tables.items():
        if tag in (b'cmap', b'head'):
            continue
        off2, size2 = tables[tag]
        assert size == size2 and (BASE / FONT).read_bytes()[offset:offset+size] == data[off2:off2+size2], tag
    # Same normalized 20x20 cell and 18px fallback generation as accepted body text.
    face = ImageFont.truetype(str(RES / FONT), 18)
    cells = []
    for code in sorted(mapping):
        image = Image.new('RGBA', (20, 20), (128,128,128,0))
        ImageDraw.Draw(image).text((1,0), chr(int(code,16)), font=face, fill=(128,128,128,252))
        assert image.getchannel('A').getbbox(), code
        cells.append((int(code,16), image))
    pack.OUT = RES
    template, addresses = pack.font_template()
    sheet = pack.make_font(template, addresses, [((0,68,102,126), cells)])
    (RES / 'candidate-sheet.fnt').write_bytes(sheet)
    decode.OUT = NATIVE
    loaded = decode.decode_original(sheet, 0)
    run = subprocess.run([str(ROOT / 'tools/render_cn7_font.exe'), '--sheet',
        str((RES / FONT).relative_to(ROOT)), str((RES / 'candidate-sheet.fnt').relative_to(ROOT)),
        str((NATIVE / 'extra-0-0.rgba').relative_to(ROOT)), '0',
        str((NATIVE / 'shared-candidates.rgba').relative_to(ROOT))],
        capture_output=True, text=True, check=True)
    (NATIVE / 'shared-candidates.tsv').write_text(run.stdout, 'utf-8')
    lines = run.stdout.splitlines()
    _, w, h = lines[0].split('\t')
    atlas = Image.frombytes('RGBA', (int(w),int(h)), (NATIVE / 'shared-candidates.rgba').read_bytes())
    atlas.putalpha(atlas.getchannel('A').point(lambda a: min(255,a*2)))
    rendered, metrics = {}, {}
    for line in lines[1:]:
        code, x, y, w, h, top, bottom = line.split('\t')
        x, y, w, h, top, bottom = map(int, (x,y,w,h,top,bottom))
        rendered[code] = atlas.crop((x*4,y*4,(x+w)*4,(y+h)*4)).getchannel('A')
        metrics[code] = {'advance': w, 'height': h, 'top': top, 'bottom': bottom}
        assert rendered[code].getbbox() and w == h == 20, code
    assert set(rendered) == set(mapping), 'No fallback or missing native glyph allowed'
    old = read(ROOT / 'cn7-glyph-review-184/records/新增184字索引.json')
    usage = {r['code']: r['usage'] for r in old['rows']}
    catalog = read(BASE / 'game-text/translations/ui/zh-CN.json')['labels']
    contexts, seen = defaultdict(list), defaultdict(set)
    combined = identities | mapping
    for key, row in catalog.items():
        for code in set(map(ord,row['text'])) & {int(c,16) for c in mapping}:
            keycode = f'{code:04X}'
            if len(contexts[keycode]) >= 4:
                continue
            parts = context_parts(row['text'], code, combined)
            visible = ''.join(p['text'] for p in parts)
            if visible in seen[keycode]:
                continue
            seen[keycode].add(visible)
            contexts[keycode].append({'parts': parts, 'english': row['original'][:400], 'id': key})
    pairs, rows = {}, []
    for index, (code,ch) in enumerate(sorted(mapping.items()),1):
        raw = reverse[code]
        member, plane, u, v, levels = sources[raw]
        source = Image.open(ROOT / f'cn5-glyph-fix1-verification/original-ISO-decoded/font-{member}-plane-{plane}.png').convert('RGBA')
        x,y,w,h = u&1023,v&1023,(u>>10)&31,(v>>10)&31
        original = source.crop((x,y,x+w,y+h)).getchannel('A')
        new = rendered[code]
        pair = pair_picture(original, new, True)
        left, right = pair.crop((0,0,104,104)), pair.crop((104,0,208,104))
        assert left.tobytes() != right.tobytes(), ('Unchanged pair', code)
        pairs[code] = pair
        encoded = io.BytesIO()
        pair.save(encoded, 'PNG')
        row = {'index': index, 'code': code, 'rawCode': raw, 'identity': ch, 'identityLabel': ch,
            'previous': None, 'group': 'mapped', 'suspect': code in PRIORITY, 'fixed': False,
            'source': '左：汉化ISO原字形；右：寒蝉圆黑体·粗体候选，使用游戏原生C渲染器4倍生成；待你校对，尚未应用到游戏',
            'usage': usage[code], 'contexts': contexts[code],
            'image': 'data:image/png;base64,'+base64.b64encode(encoded.getvalue()).decode('ascii'),
            'source_alpha_sha256': sha(original.tobytes()), 'native_alpha_sha256': sha(new.tobytes()),
            'unicode_candidate': f'U+{ord(ch):04X}', 'native_metrics': metrics[code],
            'user_reviewed': False}
        row['search'] = ' '.join([code,raw,ch]+[''.join(p['text'] for p in c['parts'])+' '+c['english'] for c in row['contexts']]).lower()
        rows.append(row)
    font_hash = sha(data)
    dataset = {'id': 'CN7-HD184-'+font_hash[:12], 'fontHash': font_hash, 'mapped': 184, 'rows': rows}
    html = (ROOT / 'tools/glyph_review_template.html').read_text('utf-8')
    html = html.replace('电光火石3 · 全字库核对', '电光火石3 · 新增184字 · 圆黑粗体核对')
    html = html.replace('左看原字，右看高清字；用字码反馈，无需在游戏里逐句寻找。',
        '左侧是原汉化字形，右侧已全部换成寒蝉圆黑体·粗体。比较是否同一个字，有误才需要填写修正。')
    html = html.replace('全部已加载字形', '本次新增字形').replace('自定义字码 · 重点核对', '已生成新字体')
    html = re.sub(r'<details>.*?</details>',
        '<details open><summary>怎么核对、如何保存</summary><p>184个字都已识别并生成圆黑粗体候选。左侧为汉化ISO原字形，'
        '右侧为游戏原生C字体渲染器的4倍输出，并非浏览器替代字。左右是同一个字就选“正确”；不同则填写应有的一个字。'
        '可以点“放大 / 看例句”，原英文也会一起显示。</p><p>候选字尚未得到你的确认，标有“重点复核”的字可优先检查。'
        '完成后点“导出修改表”，把JSON发回；如果全部正确，直接告诉我即可。中途退出请点“保存全部进度”。'
        '这份表仅预览新字形，不会改动游戏或存档。</p></details>', html, count=1, flags=re.S)
    html = html.replace('<section class="toolbar">', '<section class="toolbar" id="toolbar">')
    html = html.replace('当前高清字形', '圆黑粗体候选').replace('当前游戏渲染', '圆黑粗体候选')
    html = html.replace("?'当前映射'", "?'识别候选'")
    html = html.replace('重复映射提示', '重点复核').replace('重复映射', '重点复核').replace('重复字提示', '候选字重点复核')
    html = html.replace('BT3-字库修改表.json', 'BT3-CN7-184字圆黑核对修改表.json')
    html = html.replace('BT3-字库核对进度.json', 'BT3-CN7-184字圆黑核对进度.json')
    html = re.sub(r"\$\('footnote'\)\.textContent=`[^`]*`;",
        "$('footnote').textContent=`CN7新增184字 · 全部右侧为原生C渲染的圆黑粗体候选；尚未应用到游戏。字库数据版本 ${DATA.id}。完全离线，图片均已内嵌。`;",html)
    html = html.replace('__GLYPH_DATA__', json.dumps(dataset,ensure_ascii=False,separators=(',',':')).replace('<','\\u003c'))
    page = OUT / '新增184字核对-圆黑粗体.html'
    page.write_text(html, 'utf-8')
    lean = {**dataset, 'rows': [{k:v for k,v in r.items() if k not in ('image','search')} for r in rows]}
    write(RECORDS / '新增184字圆黑核对索引.json',lean)
    write(RECORDS / '候选字映射.json',mapping)
    write(RES / 'font-identities.json', combined)
    title = ImageFont.truetype(r'C:\Windows\Fonts\msyh.ttc',25)
    label = ImageFont.truetype(r'C:\Windows\Fonts\msyh.ttc',16)
    for start in range(0,184,64):
        batch = rows[start:start+64]
        proof = Image.new('RGB',(8*220,90+math.ceil(len(batch)/8)*158),'#eff4fa')
        draw = ImageDraw.Draw(proof)
        draw.text((16,10),f'新增184字 · {start+1}–{start+len(batch)} · 左：原汉化　右：寒蝉圆黑粗体候选',font=title,fill='#143f6e')
        for n,row in enumerate(batch):
            x,y = (n%8)*220,90+(n//8)*158
            draw.text((x+8,y),f"#{row['index']:03d} {row['code']}  {row['identity']}",font=label,fill='#134c98')
            proof.paste(pairs[row['code']],(x+6,y+25))
            draw.text((x+8,y+132),'重点复核' if row['suspect'] else '原字形 / 圆黑粗体',font=label,fill='#6b5d13' if row['suspect'] else '#536b82')
        proof.save(OUT / '对照图' / f'原字与圆黑粗体-{start//64+1:02d}.png')
    manifest = {'edition':'CN7 new184 HD review', 'dataset':dataset['id'], 'glyphs':len(rows),
        'native_rounded_bold_glyphs_rendered':len(rendered), 'fallback_or_missing_glyphs':0,
        'all_184_pair_images_differ':True, 'source_ISO_pixels_exact':True,
        'font_cmap_additions_only':184, 'old_font_mappings_outlines_metrics_unchanged':True,
        'uniform_cell_advance_and_height':20, 'priority_review_codes':sorted(PRIORITY),
        'candidate_font_sha256':font_hash, 'official_reviewed_font_sha256':sha((BASE/FONT).read_bytes()),
        'user_confirmed_new_identities':0, 'candidate_identity_status':'manual transcription plus sentence context; requires user review',
        'game_files_modified':False, 'game_launched':False, 'runtime_code_modified':False,
        'self_contained_offline_HTML':True}
    write(RECORDS / 'manifest.json',manifest)
    (OUT / '使用说明.txt').write_text('打开“新增184字核对-圆黑粗体.html”。\n'
        '左边为原字，右边184字已全部生成寒蝉圆黑体·粗体候选。\n'
        '左右相同可选正确；不同才需要填修正字。完成后导出修改表JSON发回；全部正确也可直接告知。\n'
        '长时间核对请保存全部进度，下次读取。新字体暂用于这份表，未覆盖游戏，核对后再统一应用。\n','utf-8-sig')
    print('PASS: 184/184 native rounded-bold glyphs rendered; no missing/fallback; old mappings unchanged')
    print('Review page:',page)


if __name__ == '__main__':
    main()
