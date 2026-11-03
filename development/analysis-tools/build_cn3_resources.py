"""CN3 catalogs, boot glyphs, and OFL font adaptation; never writes an installation."""
from pathlib import Path
from collections import defaultdict, Counter
import copy, hashlib, json, os, shutil, struct, unicodedata
from PIL import Image, ImageDraw, ImageFont
import build_cn2_adapter as pack
import upstream_extract_eu_text as disc
from make_vector_font_options import font_coverage
from render_cn_samples import u32

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'cn3-resources'
BASE=ROOT/'cn2-resources'
FONT=ROOT/'cn3-font-options/vendor/ChillRoundGothic_Bold.ttf'
FONT_NAME='bt3cn-rounded-bold.ttf'

def read(p): return json.loads(p.read_text('utf-8'))
def write(p,v):
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n','utf-8')

def cmap(data):
    n=struct.unpack_from('>H',data,4)[0]
    tables={data[12+i*16:16+i*16]:struct.unpack_from('>II',data,20+i*16) for i in range(n)}
    off,_=tables[b'cmap'];count=struct.unpack_from('>H',data,off+2)[0];maps=[]
    for i in range(count):
        _,_,sub=struct.unpack_from('>HHI',data,off+4+i*8); sub+=off
        fmt=struct.unpack_from('>H',data,sub)[0];result={}
        if fmt==12:
            for j in range(struct.unpack_from('>I',data,sub+12)[0]):
                start,end,gid=struct.unpack_from('>III',data,sub+16+j*12)
                result.update({c:gid+c-start for c in range(start,end+1) if gid+c-start})
        elif fmt==4:
            seg=struct.unpack_from('>H',data,sub+6)[0]//2
            ends=sub+14;starts=ends+2*seg+2;deltas=starts+2*seg;ranges=deltas+2*seg
            for j in range(seg):
                end=struct.unpack_from('>H',data,ends+2*j)[0];start=struct.unpack_from('>H',data,starts+2*j)[0]
                delta=struct.unpack_from('>h',data,deltas+2*j)[0];rel=struct.unpack_from('>H',data,ranges+2*j)[0]
                for c in range(start,min(end,0xfffe)+1):
                    gid=struct.unpack_from('>H',data,ranges+2*j+rel+2*(c-start))[0] if rel else (c+delta)&65535
                    if rel and gid: gid=(gid+delta)&65535
                    if gid: result[c]=gid
        if result:maps.append(result)
    result={}
    for m in sorted(maps,key=len):result.update(m)
    return tables,result

def checksum(b):
    b+=bytes(-len(b)%4)
    return sum(struct.unpack('>'+str(len(b)//4)+'I',b))&0xffffffff

def derive_font(mapping):
    data=FONT.read_bytes();tables,char_map=cmap(data);before=dict(char_map)
    remapped={int(c,16):ord(v) for c,v in mapping.items() if len(v)==1 and ord(v) in char_map}
    for code,actual in remapped.items():char_map[code]=before[actual]
    # A single complete Unicode format-12 map is accepted by the port's checked
    # font reader. Original glyph outlines/metrics/kerning remain byte identical.
    groups=[]
    for code,gid in sorted(char_map.items()):
        if groups and code==groups[-1][1]+1 and gid==groups[-1][2]+code-groups[-1][0]:groups[-1][1]=code
        else:groups.append([code,code,gid])
    sub=struct.pack('>HHIII',12,0,16+12*len(groups),0,len(groups))+b''.join(struct.pack('>III',*g) for g in groups)
    new_cmap=struct.pack('>HHHHIHHI',0,2,0,4,20,3,10,20)+sub
    payload={tag:data[off:off+size] for tag,(off,size) in tables.items() if tag!=b'DSIG'}
    payload[b'cmap']=new_cmap
    # Rename the derivative, retaining copyright, license and manufacturer.
    old=payload[b'name'];fmt,count,string_off=struct.unpack_from('>HHH',old);names=[];strings=bytearray()
    replacements={1:'BT3CN Rounded',2:'Bold',3:'BT3CN Rounded Bold Local 2026',4:'BT3CN Rounded Bold',6:'BT3CN-Rounded-Bold',16:'BT3CN Rounded',17:'Bold'}
    for i in range(count):
        platform,enc,lang,name,length,at=struct.unpack_from('>HHHHHH',old,6+12*i)
        value=old[string_off+at:string_off+at+length]
        if name in replacements:value=replacements[name].encode('utf-16be' if platform in (0,3) else 'ascii')
        names.append(struct.pack('>HHHHHH',platform,enc,lang,name,len(value),len(strings)));strings.extend(value)
    payload[b'name']=struct.pack('>HHH',0,len(names),6+12*len(names))+b''.join(names)+strings
    head=bytearray(payload[b'head']);struct.pack_into('>I',head,8,0);payload[b'head']=bytes(head)
    tags=sorted(payload);n=len(tags);power=1<<(n.bit_length()-1)
    font=bytearray(struct.pack('>IHHHH',0x10000,n,power*16,power.bit_length()-1,n*16-power*16)+bytes(16*n))
    offsets={}
    for i,tag in enumerate(tags):
        value=payload[tag];off=len(font);offsets[tag]=off
        struct.pack_into('>4sIII',font,12+16*i,tag,checksum(value),off,len(value))
        font.extend(value);font.extend(bytes(-len(font)%4))
    struct.pack_into('>I',font,offsets[b'head']+8,(0xb1b0afba-checksum(bytes(font)))&0xffffffff)
    assert checksum(bytes(font))==0xb1b0afba and len(font)<16*1024*1024
    path=OUT/'fonts'/FONT_NAME;path.write_bytes(font)
    check_tables,check_map=cmap(bytes(font))
    assert all(check_map[c]==before[c] for c in before if not 0xe000<=c<=0xf8ff)
    for tag in (b'glyf',b'loca',b'hmtx',b'hhea',b'kern'):
        if tag in tables:assert payload[tag]==data[tables[tag][0]:sum(tables[tag])]
    assert all(check_map[c]==before[v] for c,v in remapped.items())
    return remapped

def identify_safe_glyphs():
    p=ROOT/'cn3-glyph-mapping';audit=read(p/'audit.json');mapping=read(p/'manual-map.json')
    known=read(ROOT/'cn3-body-font-options/records/sample-glyph-identities.json')['encoded_to_Unicode']
    overrides=read(p/'manual-overrides.json');norm=lambda s:unicodedata.normalize('NFKC',s)
    # Recognition is only supporting evidence for manual transcription. Keep
    # original pixels for ambiguous readings instead of guessing a replacement.
    accepted={c:v for c,v in mapping.items() if c in known or c in overrides or
              norm(v) in {norm(s) for s in audit['ocr'].get(c,{}).values()}}
    pending={c:v for c,v in mapping.items() if c not in accepted}
    write(OUT/'font-identities.json',accepted);write(OUT/'font-pending-identities.json',pending)
    return accepted,pending

def boot_fonts(catalog):
    glyphs={}
    for i in range(1,8):
        for c,g in pack.decode_font(i).items():glyphs.setdefault(c,g)
    rawmap={int(k,16):int(v,16) for k,v in read(BASE/'font-code-map.json').items()}
    extra={new:glyphs[old] for old,new in rawmap.items() if old in glyphs}
    native=disc.sections((pack.GAME/'gamedata/pzs3us1/00004.bin').read_bytes())
    native_codes=set()
    for data in native[:2]:
        table,count=u32(data,20),u32(data,24)
        native_codes.update(struct.unpack_from('<H',data,table+i*6)[0] for i in range(count))
    needed={ord(c) for v in catalog['labels'].values() for c in v['text'] if ord(c)>=32 and ord(c) not in (0xfeff,0xa0)}
    font=ImageFont.truetype(str(FONT),18)
    if 0xb7 in rawmap:
        image=Image.new('RGBA',(10,20),(128,128,128,0))
        ImageDraw.Draw(image).text((0,-2),'·',font=font,fill=(128,128,128,252));extra[rawmap[0xb7]]=image
    unsupported=needed-set(extra)-native_codes
    coverage=font_coverage(FONT)
    for code in sorted(unsupported):
        assert code in coverage,f'No real outline: {code:04X}'
        image=Image.new('RGBA',(19,20),(128,128,128,0))
        ImageDraw.Draw(image).text((0,-2),chr(code),font=font,fill=(128,128,128,252))
        assert image.getchannel('A').getbbox() is not None or chr(code).isspace(),hex(code)
        extra[code]=image
    if 0xb7 in rawmap:
        image=Image.new('RGBA',(10,20),(128,128,128,0))
        ImageDraw.Draw(image).text((0,-2),'·',font=font,fill=(128,128,128,252));extra[rawmap[0xb7]]=image
    pack.OUT=OUT;template,addresses=pack.font_template()
    groups=defaultdict(list)
    for code,glyph in sorted(extra.items()):groups[glyph.info.get('gs_alpha_levels',(0,68,102,126))].append((code,glyph))
    capacity=(512//21)**2
    planes=[(levels,glyphs[i:i+capacity]) for levels,glyphs in sorted(groups.items()) for i in range(0,len(glyphs),capacity)]
    fonts=[pack.make_font(template,addresses,planes[i:i+2]) for i in range(0,len(planes),2)]
    assert len(fonts)<=5
    parts=list(native);parts[2:7]=fonts+[b'']*(5-len(fonts))
    result=pack.boot_archive(parts)
    after=disc.sections(result)
    assert native[:2]==after[:2] and native[7:]==after[7:]
    assert needed<=set(extra)|native_codes
    (OUT/'mods/pzs3us1/00004.bin').write_bytes(result)
    return len(extra),len(unsupported),len(fonts)

def main():
    os.chdir(ROOT)
    shutil.copytree(BASE,OUT,dirs_exist_ok=True)
    for kind in ('ui','labels'):
        shutil.copy2(ROOT/f'terminology-review/staged/game-text/translations/{kind}/zh-CN.json',OUT/f'game-text/translations/{kind}/zh-CN.json')
    catalog=read(OUT/'game-text/translations/ui/zh-CN.json')
    accepted,pending=identify_safe_glyphs()
    remapped=derive_font(accepted)
    (OUT/'fonts/fonts.tsv').write_text(FONT_NAME+'\t寒蝉圆黑体·粗体（本地适配）\t3\n','utf-8')
    shutil.copy2(ROOT/'cn3-font-options/vendor/ChillRoundGothic-OFL.txt',OUT/'fonts/OFL.txt')
    extra,unicode_added,sheets=boot_fonts(catalog)
    # Catalog-driven native menu labels run before original-art fallback. No
    # need to alter menu archives or networking for these words to take effect.
    for name in ('labels.tsv','labels.json','name-styles.tsv'):
        shutil.copy2(ROOT/'CN2-Preview/Tenkaichi3Decomp/gamedata/game-text'/name,OUT/'game-text'/name)
    freq=Counter(ord(c) for v in catalog['labels'].values() for c in v['text'] if 0xe000<=ord(c)<=0xf8ff)
    write(OUT/'cn3-manifest.json',{'edition':'r5-CN3','font':'寒蝉圆黑体·粗体',
        'font_source_sha256':hashlib.sha256(FONT.read_bytes()).hexdigest(),
        'font_private_codes_with_verified_mapping':len(remapped),
        'ambiguous_private_codes_keep_original_glyphs':len(pending),
        'private_code_occurrence_vector_coverage':sum(n for c,n in freq.items() if c in remapped)/sum(freq.values()),
        'extra_glyphs':extra,'supplemental_Unicode_glyphs':unicode_added,'font_sheets':sheets,
        'training_rows':398,'confirmed_terminology_rules':12,'original_game_announcements_preserved':True,
        'network_or_protocol_edits':False,'protocol':5})
    print(json.dumps(read(OUT/'cn3-manifest.json'),ensure_ascii=False,indent=2))

if __name__=='__main__':main()
