"""Build a standalone offline review of every glyph in the active game fonts.

The first 1,956 entries compare exact ISO bitmaps to the port's native C
rasterizer. No OCR guesses or browser-font substitutions are used as truth.
"""
from pathlib import Path
from collections import defaultdict,Counter
import base64,hashlib,io,json,math,struct,unicodedata
from PIL import Image,ImageDraw,ImageFont
import upstream_extract_eu_text as disc

ROOT=Path(__file__).resolve().parents[1]
RES=ROOT/'cn5-glyph-fix1-resources'
NATIVE=ROOT/'cn5-glyph-fix1-verification'
OUT=ROOT/'glyph-review-20261023'
BASE=ROOT/'cn5-resources'
FIXES={'E2C2':'您','E510':'拳'}
def read(path):return json.loads(path.read_text('utf-8'))
def write(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n','utf-8')
def sha(data):return hashlib.sha256(data).hexdigest()
def records(data):
    table,count=struct.unpack_from('<II',data,20)
    return [struct.unpack_from('<HHH',data,table+6*i) for i in range(count)]
def crop(rows,sheets):
    result={}
    for code,u,v in rows:
        x,y,w,h=u&1023,v&1023,(u>>10)&31,(v>>10)&31
        plane=(u>>15)|((v>>15)<<1)
        result.setdefault(code,sheets[plane].crop((x,y,x+w,y+h)).getchannel('A'))
    return result
def originals():
    result={}
    for member in range(1,8):
        data=(ROOT/f'private-resources/cn-font-{member}.fnt').read_bytes();rows=records(data)
        planes={(u>>15)|((v>>15)<<1) for _,u,v in rows}
        sheets={p:Image.open(NATIVE/f'original-ISO-decoded/font-{member}-plane-{p}.png').convert('RGBA') for p in planes}
        for code,mask in crop(rows,sheets).items():result.setdefault(code,mask)
    # E000 is the intentionally supplied local middle-dot fallback, not an ISO
    # glyph. Keep its historical bitmap and disclose that exception in the UI.
    dot=next(r for r in read(ROOT/'resolution-workload-20261022/font-glyphs.json') if r['code']=='E000')
    image=Image.open(ROOT/f"resolution-workload-20261022/font-planes/font-{dot['font_member']}-plane-{dot['plane']}.png").convert('RGBA')
    x,y,w,h=[dot[k] for k in ('x','y','width','height')]
    result[0xb7]=image.crop((x,y,x+w,y+h)).getchannel('A')
    return result
def active():
    result={};locations={}
    parts=disc.sections((RES/'mods/pzs3us1/00004.bin').read_bytes())
    for member,data in enumerate(parts[:7]):
        if not data:continue
        rows=records(data);planes={(u>>15)|((v>>15)<<1) for _,u,v in rows};sheets={}
        texture=struct.unpack_from('<I',data,12)[0];tex0=struct.unpack_from('<Q',data,texture+48)[0]
        width,height=1<<((tex0>>26)&15),1<<((tex0>>30)&15)
        for plane in planes:
            raw=(NATIVE/f'extra-{member}-{plane}.rgba').read_bytes();assert len(raw)==width*height*4
            image=Image.frombytes('RGBA',(width,height),raw)
            image.putalpha(image.getchannel('A').point(lambda a:min(255,a*2)));sheets[plane]=image
        for code,mask in crop(rows,sheets).items():
            result.setdefault(code,mask);locations.setdefault(code,member)
    return result,locations
def native():
    result={}
    for table in sorted(NATIVE.glob('shared-*.tsv')):
        if table.name.endswith('.metrics.tsv'):continue
        lines=table.read_text('utf-8').splitlines();_,w,h=lines[0].split('\t')
        image=Image.frombytes('RGBA',(int(w),int(h)),table.with_suffix('.rgba').read_bytes())
        image.putalpha(image.getchannel('A').point(lambda a:min(255,a*2)))
        for line in lines[1:]:
            code,x,y,w,h,_,_=line.split('\t');x,y,w,h=map(int,(x,y,w,h))
            result[int(code,16)]=image.crop((x*4,y*4,(x+w)*4,(y+h)*4)).getchannel('A')
    return result
def cleaned(mask):
    box=mask.getbbox()
    if not box:return None
    mask=mask.crop(box)
    peak=mask.getextrema()[1]
    return mask.point(lambda a:round(a*255/peak))
def pair_picture(original,current,vector):
    canvas=Image.new('RGB',(208,104),'white');draw=ImageDraw.Draw(canvas)
    draw.line((104,5,104,99),fill='#e7edf5')
    for i,(mask,is_vector) in enumerate(((original,False),(current,vector))):
        mask=cleaned(mask)
        if mask is None:
            draw.rectangle((i*104+34,34,i*104+70,70),outline='#dbe4ef');continue
        if is_vector:
            if max(mask.size)>84:
                mask.thumbnail((84,84),Image.Resampling.LANCZOS)
        else:
            factor=max(1,min(4,int(min(84/mask.width,84/mask.height))))
            mask=mask.resize((mask.width*factor,mask.height*factor),Image.Resampling.NEAREST)
        x=i*104+(104-mask.width)//2;y=(104-mask.height)//2
        canvas.paste((17,31,50),(x,y),mask)
    return canvas
def label(identity,code):
    if identity==' ':return '空格'
    if identity=='\u3000':return '全角空格'
    if identity.isspace():return '空白符'
    if not identity or unicodedata.category(identity).startswith('C'):return 'U+'+code
    return identity
def context_parts(raw,code,mapping):
    i=raw.index(chr(code));start=max(0,i-14);end=min(len(raw),i+15)
    parts=[]
    for char in raw[start:end]:
        hit=ord(char)==code;text=mapping.get(f'{ord(char):04X}',char)
        if parts and parts[-1]['hit']==hit:parts[-1]['text']+=text
        else:parts.append({'text':text,'hit':hit})
    if start:parts.insert(0,{'text':'…','hit':False})
    if end<len(raw):parts.append({'text':'…','hit':False})
    return parts

def main():
    # Only regenerate the same dataset, leaving exported user progress alone.
    if (OUT/'records/manifest.json').exists():
        assert read(OUT/'records/manifest.json')['font_sha256']==sha((RES/'fonts/bt3cn-rounded-bold.ttf').read_bytes())
    OUT.mkdir(exist_ok=True);(OUT/'对照图').mkdir(exist_ok=True);(OUT/'records').mkdir(exist_ok=True)
    mapping=read(RES/'font-identities.json');previous=read(BASE/'font-identities.json')
    rawmap=read(RES/'font-code-map.json');rawcodes={int(v,16):int(k,16) for k,v in rawmap.items()}
    iso=originals();loaded,locations=active();rendered=native()
    assert len(loaded)==3249 and len(mapping)==1956 and set(rawcodes)=={int(c,16) for c in mapping}
    assert set(rawcodes)<=loaded.keys() and set(rawcodes.values())<=iso.keys()
    assert len(rendered)==2637
    byidentity=defaultdict(list)
    for code,identity in mapping.items():
        if unicodedata.category(identity).startswith('L'):
            byidentity[unicodedata.normalize('NFKC',identity)].append(code)
    duplicate_groups={identity:codes for identity,codes in byidentity.items() if len(codes)>1 and
                      len({sha(cleaned(iso[rawcodes[int(c,16)]]).tobytes()) for c in codes})>1}
    suspects={c for codes in duplicate_groups.values() for c in codes}
    catalog=read(RES/'game-text/translations/ui/zh-CN.json')['labels'];usage=Counter();contexts=defaultdict(list);seen=defaultdict(set)
    for key,row in catalog.items():
        raw=row['text']
        for code in set(map(ord,raw))&loaded.keys():
            usage[code]+=1
            if len(contexts[code])>=4:continue
            parts=context_parts(raw,code,mapping);visible=''.join(p['text'] for p in parts)
            if visible in seen[code]:continue
            seen[code].add(visible);contexts[code].append({'parts':parts,'english':row['original'][:220],'id':key})
    order=sorted(rawcodes)+sorted(loaded.keys()-rawcodes.keys());rows=[];pairs={}
    for index,code in enumerate(order,1):
        key=f'{code:04X}';mapped=code in rawcodes;identity=mapping.get(key,chr(code))
        source=iso[rawcodes[code]] if mapped else loaded[code]
        right=rendered.get(code,loaded[code]);pair=pair_picture(source,right,code in rendered)
        pairs[key]=pair;encoded=io.BytesIO();pair.save(encoded,'PNG')
        row={'index':index,'code':key,'rawCode':f'{rawcodes[code]:04X}' if mapped else None,
          'identity':identity,'identityLabel':label(identity,key),'previous':previous.get(key),
          'group':'mapped' if mapped else 'other','suspect':key in suspects,'fixed':key in FIXES,
          'source':('本地补充的间隔点（不是 ISO 原字形）' if key=='E000' else '汉化 ISO 自定义字码' if mapped else '美版原字库（保持原样）' if locations[code]<2 else '直接 Unicode 字符（无需自定义识别）'),
          'usage':usage[code],'contexts':contexts[code],
          'image':'data:image/png;base64,'+base64.b64encode(encoded.getvalue()).decode('ascii'),
          'source_alpha_sha256':sha(source.tobytes()),'native_alpha_sha256':sha(right.tobytes())}
        row['search']=' '.join([key,'U+'+key,row['rawCode'] or '',identity]+[''.join(p['text'] for p in c['parts']) for c in row['contexts']]).lower()
        rows.append(row)
    font_hash=sha((RES/'fonts/bt3cn-rounded-bold.ttf').read_bytes())
    dataset={'id':'CN5-G1-'+font_hash[:12],'fontHash':font_hash,'mapped':len(mapping),'rows':rows}
    html=(ROOT/'tools/glyph_review_template.html').read_text('utf-8')
    html=html.replace('__GLYPH_DATA__',json.dumps(dataset,ensure_ascii=False,separators=(',',':')).replace('<','\\u003c'))
    page=OUT/'全字库核对.html';page.write_text(html,'utf-8')
    # JSON/CSV without inline images supplies stable codes for manual review and
    # future batch corrections, independently of the browser.
    lean={k:v for k,v in dataset.items() if k!='rows'};lean['rows']=[{k:v for k,v in r.items() if k not in ('image','search')} for r in rows]
    write(OUT/'records/全字库索引.json',lean)
    write(OUT/'records/重复映射提示.json',duplicate_groups)
    for path in ['font-identities.json','font-code-map.json']:(OUT/'records'/path).write_bytes((RES/path).read_bytes())
    font=ImageFont.truetype(r'C:\Windows\Fonts\msyh.ttc',18)
    small=ImageFont.truetype(r'C:\Windows\Fonts\msyh.ttc',14)
    title=ImageFont.truetype(r'C:\Windows\Fonts\msyh.ttc',25)
    page_count=0
    for group,prefix in [('mapped','重点字库'),('other','其他字形')]:
        subset=[r for r in rows if r['group']==group]
        for start in range(0,len(subset),96):
            part=subset[start:start+96];cols=8;cw,ch=220,158;height=90+math.ceil(len(part)/cols)*ch
            canvas=Image.new('RGB',(cols*cw,height),'#f1f5fa');draw=ImageDraw.Draw(canvas)
            number=start//96+1
            draw.text((16,10),f'{prefix} · 第 {number:02d} 页 · {start+1}–{start+len(part)} / {len(subset)}',font=title,fill='#1c3557')
            draw.text((16,50),'每格：左侧原汉化字形（其他字形为点阵后备）／右侧当前渲染。反馈示例：E252=恕。',font=font,fill='#617087')
            for i,row in enumerate(part):
                x=(i%cols)*cw;y=90+(i//cols)*ch
                draw.rounded_rectangle((x+3,y+2,x+cw-3,y+ch-4),8,fill='white',outline='#d8e2ef')
                draw.text((x+10,y+7),f"#{row['index']:04d}  {row['code']}",font=small,fill='#1654a4')
                canvas.paste(pairs[row['code']],(x+6,y+31))
                suffix=' 已修复' if row['fixed'] else ' 重复映射' if row['suspect'] else ''
                draw.text((x+9,y+133),'当前：'+row['identityLabel']+suffix,font=small,fill='#314965')
            canvas.save(OUT/'对照图'/f'{prefix}-{number:02d}.png');page_count+=1
    chosen=['E2C2','E510','E252','E406','E6B7'];sample=Image.new('RGB',(1100,210),'#eff4fa');d=ImageDraw.Draw(sample)
    for i,key in enumerate(chosen):
        row=next(r for r in rows if r['code']==key);x=i*220
        d.text((x+10,8),key+'  当前：'+row['identityLabel'],font=font,fill='#153b6b')
        d.text((x+20,39),'原字         当前',font=small,fill='#617087')
        sample.paste(pairs[key],(x+6,68))
        d.text((x+10,177),'已修复' if row['fixed'] else '供对照检查',font=small,fill='#48745a')
    sample.save(OUT/'使用示例.png')
    manifest={'dataset':dataset['id'],'active_unique_glyphs':len(rows),'custom_code_glyphs':len(mapping),
      'direct_Unicode_and_original_glyphs':len(rows)-len(mapping),'native_rendered_glyphs':len(rendered),
      'original_ISO_source_glyphs_complete':True,'synthetic_middle_dot_exception':'E000 / U+00B7; historical local fallback shown',
      'all_loaded_font_codes_present':set(order)==set(loaded),
      'duplicate_mapping_groups_for_review_only':len(duplicate_groups),'duplicate_flagged_codes':len(suspects),
      'contact_sheet_count':page_count,'font_sha256':font_hash,'self_contained_HTML':True,
      'original_US_fonts_unchanged':True,'game_launched':False,'scope':'All unique codes in active boot font members 0..6; artwork text is separate',
      'corrected':read(NATIVE/'glyph-corrections.json')}
    write(OUT/'records/manifest.json',manifest)
    (OUT/'使用说明.txt').write_text('双击“全字库核对.html”，用浏览器打开即可，完全离线。\n'
      '重点核对 1956 个自定义字码；全部已加载字库共 3249 个字形，另含 1293 个直接编码或原版字形。\n'
      '左侧为原字，右侧为当前游戏的实际高清渲染。可按字码、文字和例句搜索，点击放大。\n'
      '有误时填写正确的字，或标记存疑。核对后点“导出修改表”，把 JSON 文件发回。\n'
      '中途退出前点“保存全部进度”，下次“读取进度”继续；不要只依赖浏览器缓存。\n'
      '不使用网页也可直接查看“对照图”中的 35 张编号大图，并反馈 E252=恕 这样的字码列表。\n'
      '您/拳已纠正；真正的怨/舞各自保留。重复映射只是检查提示，不代表已经确认错字。\n'
      '这份清单检查自定义字码映射，不替代翻译措辞校对；图片上画死的文字不属于共享字库。\n','utf-8-sig')
    print(json.dumps(manifest,ensure_ascii=False,indent=2));print('Review page:',page)

if __name__=='__main__':main()
