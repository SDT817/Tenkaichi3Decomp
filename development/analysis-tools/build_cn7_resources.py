"""Extend accepted Chinese assets; never alter scripts, music or installed data."""
from collections import Counter,defaultdict
from pathlib import Path
import copy,hashlib,json,os,shutil,struct
from PIL import Image,ImageDraw,ImageFont
import upstream_extract_eu_text as disc
import build_cn2_adapter as pack
import build_cn3_resources as font_tools
from cn7_text_fixes import TOURNAMENT_EXTRA,SKILL_CONTEXT,SKILL_TERMS,PRESERVE_ART

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'cn6-resources'
RES=ROOT/'cn7-resources'
ANALYSIS=ROOT/'cn7-analysis'

def read(path):return json.loads(path.read_text('utf-8'))
def write(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n','utf-8')
def sha(data):return hashlib.sha256(data).hexdigest()
def fnv(data):
    h=14695981039346656037
    for b in data:h=((h^b)*1099511628211)&0xffffffffffffffff
    return f'{h:016x}'

def main():
    assert not RES.exists(),'Keep completed resource editions immutable'
    os.chdir(ROOT);shutil.copytree(BASE,RES)
    identity=read(BASE/'font-identities.json')
    def readable(s):return ''.join(identity.get(f'{ord(c):04X}',c) for c in s)
    rawmap=read(BASE/'font-code-map.json')
    _,fontmap=font_tools.cmap((BASE/'fonts/bt3cn-rounded-bold.ttf').read_bytes())
    nextcode=max(int(v,16) for v in rawmap.values())+1
    new_codes={}
    for rawcode in sorted(read(ANALYSIS/'story-unknown-codes.json')):
        while nextcode in fontmap:nextcode+=1
        assert nextcode<=0xf8ff
        new_codes[rawcode]=f'{nextcode:04X}';nextcode+=1
    rawmap.update(new_codes)
    def encode(s):
        return ''.join(chr(int(rawmap[f'{ord(c):04X}'],16)) if f'{ord(c):04X}' in rawmap else
                       (' ' if ord(c)==0xa0 else c) for c in s)
    ui=read(BASE/'game-text/translations/ui/zh-CN.json')
    en=read(BASE/'game-text/translations/ui/en.json')
    before=copy.deepcopy(ui['labels'])
    canon={}
    for i,text in TOURNAMENT_EXTRA.items():
        key=f'pzs3us1/00450/1/19/{i}'
        original=ui['labels'][key]['original']
        assert original not in canon or canon[original]==text,(i,original)
        canon[original]=text
    canon.update(SKILL_TERMS)
    for key,row in ui['labels'].items():
        if row['original'] in canon:row['text']=canon[row['original']]
        # Preserve private codes around the renamed term, including descriptions.
        while '野性感应' in readable(row['text']):
            at=readable(row['text']).index('野性感应')
            row['text']=row['text'][:at]+'野性直觉'+row['text'][at+4:]
    old_variants=defaultdict(set)
    for row in ui['labels'].values():old_variants[row['original']].add(row['text'])
    chinese={r['jp_index']-528:r['lines'] for r in read(ANALYSIS/'story-banks-complete.json')}
    english={r['us_index']-560:r['lines'] for r in read(ANALYSIS/'story-USA.json') if r['us_index']<610}
    provenance=[]
    assert chinese.keys()==english.keys()==set(range(50))
    for story in range(50):
        assert len(chinese[story])==len(english[story])==300
        for line,(original,raw) in enumerate(zip(english[story],chinese[story])):
            key=f'pzs3us1/{560+story:05d}/{line}'
            text=encode(raw) if raw.strip() and original.strip() else original
            variants=old_variants.get(original,set())
            if len(variants)==1 and original not in variants:text=next(iter(variants))
            assert key not in ui['labels']
            ui['labels'][key]={'original':original,'text':text}
            en['labels'][key]={'original':original,'text':original}
            provenance.append({'id':key,'JP_file':f'TXT-JP-B-{story:02d}.pak',
                'JP_index':528+story,'line':line,'original':original,'text':text,'readable':readable(text)})
    for i,(original,text) in enumerate(SKILL_CONTEXT.items()):
        key=f'local/skill-context/{i}'
        ui['labels'][key]={'original':original,'text':text}
        en['labels'][key]={'original':original,'text':original}
    ui['labels_count']=len(ui['labels']);en['labels_count']=len(en['labels'])
    write(RES/'game-text/translations/ui/zh-CN.json',ui)
    write(RES/'game-text/translations/ui/en.json',en)
    write(RES/'font-code-map.json',rawmap)
    write(RES/'unreviewed-new-glyph-codes.json',new_codes)
    write(ANALYSIS/'story-translation-provenance.json',provenance)
    edits=[{'id':k,'original':r['original'],'before':readable(before[k]['text']),
            'after':readable(r['text'])} for k,r in ui['labels'].items() if k in before and before[k]!=r]
    write(RES/'cn7-text-corrections.json',edits)

    # Append new font members. All five existing font members stay exact bytes.
    parts=disc.sections((BASE/'mods/pzs3us1/00004.bin').read_bytes())
    available=set()
    for part in parts[:7]:
        if part:
            table,count=struct.unpack_from('<II',part,20)
            available.update(struct.unpack_from('<H',part,table+i*6)[0] for i in range(count))
    required={ord(c) for r in ui['labels'].values() for c in r['text'] if ord(c)>=32 and ord(c) not in (0xfeff,0xa0)}
    glyphs={};cache={};sources=read(ANALYSIS/'new-glyph-sources.json')
    for old,new in new_codes.items():
        number,plane,u,v,levels=sources[old]
        path=ROOT/f'cn5-glyph-fix1-verification/original-ISO-decoded/font-{number}-plane-{plane}.png'
        if (number,plane) not in cache:cache[number,plane]=Image.open(path).convert('RGBA')
        x,y,w,h=u&1023,v&1023,(u>>10)&31,(v>>10)&31
        image=cache[number,plane].crop((x,y,x+w,y+h))
        image.info['gs_alpha_levels']=tuple(levels)
        glyphs[int(new,16)]=image
    new_private={int(c,16) for c in new_codes.values()}
    missing=required-available-new_private
    font=ImageFont.truetype(str(RES/'fonts/bt3cn-rounded-bold.ttf'),18)
    for code in sorted(missing):
        assert code in fontmap,f'No reviewed outline for Unicode {code:04X}'
        wide=(0x3000<=code<=0x30ff or 0x3400<=code<=0x9fff or 0xff01<=code<=0xff60)
        image=Image.new('RGBA',(20 if wide else 19,20),(128,128,128,0))
        ImageDraw.Draw(image).text((1,0),chr(code),font=font,fill=(128,128,128,252))
        assert image.getchannel('A').getbbox() or chr(code).isspace()
        glyphs[code]=image
    pack.OUT=RES
    template,addresses=pack.font_template()
    grouped=defaultdict(list)
    for code,image in sorted(glyphs.items()):grouped[image.info.get('gs_alpha_levels',(0,68,102,126))].append((code,image))
    planes=[(levels,items[start:start+576]) for levels,items in sorted(grouped.items()) for start in range(0,len(items),576)]
    members=[pack.make_font(template,addresses,planes[start:start+2]) for start in range(0,len(planes),2)]
    assert len(members)<=2 and not parts[5] and not parts[6]
    for i,member in enumerate(members,5):parts[i]=member
    result=pack.boot_archive(parts)
    oldparts=disc.sections((BASE/'mods/pzs3us1/00004.bin').read_bytes())
    assert disc.sections(result)[:5]==oldparts[:5] and disc.sections(result)[7:]==oldparts[7:]
    assert required<=available|glyphs.keys()
    (RES/'mods/pzs3us1/00004.bin').write_bytes(result)
    normalized=read(BASE/'normalized-cells.json')
    for code in missing:
        if 0x3400<=code<=0x9fff:normalized[f'{code:04X}']=chr(code)
    write(RES/'normalized-cells.json',normalized)

    # Append only missing artwork cells; accepted TSV bytes remain a prefix.
    art=read(BASE/'game-text/translations/labels/zh-CN.json')
    editable=read(BASE/'game-text/labels.json')
    tsv=(BASE/'game-text/labels.tsv').read_bytes()
    faces=ImageFont.truetype(str(RES/'fonts/bt3cn-rounded-bold.ttf'),1000)
    hb=faces.getbbox('H',anchor='ls');cap_units=hb[3]-hb[1]
    textures={}
    for path in ANALYSIS.glob('us*-textures.tsv'):
        for line in path.read_text('utf-8').splitlines():
            name,w,h,hash_=line.split('\t');textures[Path(name).stem]=(name,int(w),int(h),hash_)
    newrows=[];added=[]
    styles={
        'cn7-story-chapter':('580d08','580d08','000000',0,0,'000000'),
        'cn7-story-title':('ffdc52','d79e18','1c1209',1300,0,'000000'),
        'cn7-tour-banner':('ffd47d','df763a','56221b',1700,1200,'fff2e0'),
        'cn7-tour-info':('fcebb0','c7a948','3c2d17',1200,0,'000000'),
    }
    for style,(top,bottom,outline,ow,outer,oc) in styles.items():
        rgb=lambda s:[int(s[i:i+2],16) for i in (0,2,4)]
        editable['color_styles'][style]={'top':rgb(top),'bottom':rgb(bottom),'outline':rgb(outline),
            'outline_width':ow/1000,'outer':bool(outer),'outer_color':rgb(oc),'outer_width':outer/1000,'shadow':False}
    def add(stem,row,height,key,original,text,style,visible=20):
        assert key not in art['labels']
        name,w,h,hash_=textures[stem];rgba=(ROOT/name).read_bytes();assert fnv(rgba)==hash_
        quick=fnv(b''.join(rgba[(k*w*h//64)*4:(k*w*h//64)*4+4] for k in range(64)))
        box=faces.getbbox(text,anchor='ls');cap=max(3,round(cap_units*visible/(box[3]-box[1])))
        baseline=round((height-(box[3]-box[1])*cap/cap_units)/2-box[1]*cap/cap_units)
        top,bottom,outline,ow,outer,oc=styles[style]
        fields=[hash_,w,h,row*height,height,cap,baseline,1,8,1000,0,w,0,
            top,bottom,'000000',0,outline,0,ow,outer,oc,0,'000000',0,top,'000000',0,0,0,key,quick]
        assert len(fields)==32 and (row+1)*height<=h
        newrows.append('\t'.join(map(str,fields)))
        art['labels'][key]={'original':original,'text':text}
        editable['labels'].append({'id':key,'hash':hash_,'texture_height':h,'y':row*height,
            'original':original,'enabled':True,'height':height,'cap_height':cap,'baseline':baseline,
            'align':'center','margin':8,'art_width':0,'color_style':style})
        added.append({'id':key,'texture':stem,'row':row,'height':height,'original':original,'text':text,'hash':hash_,'quick':quick})
    titles=[ui['labels'][f'pzs3us1/00460/3/5/11/{i}'] for i in range(56)]
    title_text=lambda i:readable(titles[i]['text']).replace('\n','')
    for chapter in range(8):
        r=titles[chapter]
        for stem,position in [(f'us{464+chapter}-0-2-0',0),('us460-1-9-6',chapter)]:
            add(stem,position,32,f'cn7-chapter/{chapter}/{position if stem.startswith("us460") else 8}',
                r['original'],title_text(chapter),'cn7-story-chapter')
    order=[list(range(8,11)),list(range(11,15)),list(range(15,22)),list(range(22,27)),
        [27,29,30,31,28,32,33,34]+list(range(35,43)),list(range(43,48)),list(range(48,52)),list(range(52,56))]
    for chapter,indices in enumerate(order):
        for pos,index in enumerate(indices):
            add(f'us{464+chapter}-0-2-{1+pos//4}',pos%4,64,f'cn7-story-title/{chapter}/{pos}',
                titles[index]['original'],title_text(index),'cn7-story-title',28)
    tournament=[('World Tournament','天下第一武道大会'),('World Martial Arts Big Tournament','世界武道大会'),
        ('Cell Games','沙鲁游戏'),('Otherworld Tournament','地府第一武道大会'),('Yamcha Game','雅木茶游戏')]
    for i,(original,text) in enumerate(tournament):
        add(f'us450-1-9-{i//4}',i%4,64,f'cn7-tour-banner/0/{i}',original,text,'cn7-tour-banner',28)
    for texture,labels in [(0,[('Characters','角色数量'),('Difficulty','难度')]),
                           (1,[('Matches','比赛轮数'),('Victory','冠军'),('Runner-Up','亚军')])]:
        for row,(original,text) in enumerate(labels):
            add(f'us450-1-13-{texture}',row,32,f'cn7-tour-info/{texture}/{row}',original,text,'cn7-tour-info',18)
    (RES/'game-text/labels.tsv').write_bytes(tsv+('\n'.join(newrows)+'\n').encode('utf-8'))
    art['labels_count']=len(art['labels']);write(RES/'game-text/translations/labels/zh-CN.json',art)
    write(RES/'game-text/labels.json',editable)
    write(RES/'cn7-added-labels.json',added)
    manifest={'edition':'CN7','base':'CN6 resources / user-reviewed GlyphFix2; accepted G renderer',
        'UI_rows':len(ui['labels']),'UI_groups':len({k.rsplit('/',1)[0] for k in ui['labels']}),
        'existing_UI_rows_changed':len(edits),'tournament_tables':2,'tournament_rows_per_table':246,
        'story_tables':50,'story_rows_per_table':300,'story_active_scenarios':48,
        'story_translated_rows':sum(r['original']!=r['text'] for r in provenance),
        'contextual_skill_entries':SKILL_CONTEXT,'skill_terminology':SKILL_TERMS,
        'new_artwork_rows':len(added),'total_artwork_rows':len(art['labels']),
        'preserved_result_art':list(PRESERVE_ART),'new_original_ISO_glyphs':len(new_codes),
        'new_Unicode_cells':len(missing),'new_font_members':len(members),'existing_font_members_preserved':5,
        'reviewed_font_identities_and_TTF_unchanged':True,'accepted_TSV_bytes_preserved':len(tsv),
        'scripts_music_voices_network_protocol_modified':False,'protocol':5,'game_launched':False}
    write(RES/'cn7-manifest.json',manifest)
    print(json.dumps(manifest,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
