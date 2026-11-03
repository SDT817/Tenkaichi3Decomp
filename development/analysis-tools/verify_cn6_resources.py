"""Offline full resource coverage and actual native glyph-atlas rendering."""
from pathlib import Path
import hashlib,json,os,re,struct,subprocess
from PIL import Image,ImageDraw,ImageFont
import upstream_extract_eu_text as disc
import verify_cn2_adapter as decode
import build_cn3_resources as build
from make_body_font_options import SAMPLES

ROOT=Path(__file__).resolve().parents[1]
RES=ROOT/'cn6-resources';OUT=ROOT/'cn6-verification'

def decode_original(data,index):
    table,count=struct.unpack_from('<II',data,20)
    rows=[struct.unpack_from('<HHH',data,table+i*6) for i in range(count)]
    textures={};tex=struct.unpack_from('<I',data,12)[0]
    for plane in sorted({(u>>15)|((v>>15)<<1) for _,u,v in rows}):
        d=bytearray(data);palette=struct.unpack_from('<I',d,tex+4)[0];colors=bytearray()
        for i in range(16):
            x,y=(plane&1)*8+(i&7),(plane>>1)*8+(i>>3)
            at=palette+96+(y*16+x)*4;colors.extend(d[at:at+4])
        new=len(d);d.extend(bytes(96)+colors)
        struct.pack_into('<I',d,4,tex//4)
        struct.pack_into('<II',d,tex,struct.unpack_from('<I',d,tex)[0]//4,new//4)
        file=OUT/f'extra-{index}-{plane}.texture';file.write_bytes(d);rgba=file.with_suffix('.rgba')
        run=subprocess.run([str(ROOT/'tools/decode_font_texture.exe'),str(file.relative_to(ROOT)),str(rgba.relative_to(ROOT))],check=True,capture_output=True,text=True)
        width,height=map(int,run.stdout.split())
        image=Image.frombytes('RGBA',(width,height),rgba.read_bytes())
        image.putalpha(image.getchannel('A').point(lambda a:min(255,a*2)));textures[plane]=image
    result={}
    for code,u,v in rows:
        x,y,w,h=u&1023,v&1023,(u>>10)&31,(v>>10)&31
        result.setdefault(code,textures[(u>>15)|((v>>15)<<1)].crop((x,y,x+w,y+h)))
    return result

def main():
    os.chdir(ROOT);OUT.mkdir(exist_ok=True);decode.OUT=OUT
    before=disc.sections((ROOT/'cn5-glyph-fix1-resources/mods/pzs3us1/00004.bin').read_bytes())
    parts=disc.sections((RES/'mods/pzs3us1/00004.bin').read_bytes())
    assert before[:2]==parts[:2] and before[7:]==parts[7:]
    original={};rendered={};fallback=0
    identities={int(c,16):v for c,v in json.loads((RES/'font-identities.json').read_text('utf-8')).items()}
    _,fontmap=build.cmap((RES/'fonts'/build.FONT_NAME).read_bytes())
    for member,data in enumerate(parts[:7]):
        if not data:continue
        original.update(decode_original(data,member))
        if member<2:continue
        file=OUT/f'sheet-{member}.fnt';file.write_bytes(data)
        table,count=struct.unpack_from('<II',data,20)
        planes={(u>>15)|((v>>15)<<1) for _,u,v in
                (struct.unpack_from('<HHH',data,table+6*i) for i in range(count))}
        for plane in (0,1):
            if plane not in planes:continue
            path=OUT/f'shared-{member}-{plane}.rgba'
            run=subprocess.run([str(ROOT/'tools/render_cn6_font.exe'),'--sheet',
                'cn6-resources/fonts/'+build.FONT_NAME,str(file.relative_to(ROOT)),
                f'cn6-verification/extra-{member}-{plane}.rgba',str(plane),str(path.relative_to(ROOT))],
                cwd=ROOT,capture_output=True,text=True)
            # An empty second plane produces no replacement and is valid.
            if run.returncode==14:continue
            assert run.returncode==0,run.stderr
            (OUT/f'shared-{member}-{plane}.tsv').write_text(run.stdout,'utf-8')
            lines=run.stdout.splitlines();_,w,h=lines[0].split('\t');w,h=int(w),int(h)
            image=Image.frombytes('RGBA',(w,h),path.read_bytes())
            image.putalpha(image.getchannel('A').point(lambda a:min(255,a*2)))
            image.save(path.with_suffix('.png'))
            for line in lines[1:]:
                code,x,y,gw,gh,top,bottom=line.split('\t');code=int(code,16)
                x,y,gw,gh,top,bottom=map(int,(x,y,gw,gh,top,bottom))
                assert x>=0 and y>=0 and (x+gw)*4<=w and (y+gh)*4<=h
                glyph=image.crop((x*4,y*4,(x+gw)*4,(y+gh)*4))
                if 0xe000<=code<=0xf8ff and code not in fontmap:fallback+=1
                rendered[code]=(glyph,gw,top)
    ui=json.loads((RES/'game-text/translations/ui/zh-CN.json').read_text('utf-8'))['labels']
    required={ord(c) for row in ui.values() for c in row['text'] if ord(c)>=32 and ord(c) not in (0xfeff,0xa0)}
    assert required<=original.keys(),sorted(required-original.keys())
    training={k:v for k,v in ui.items() if k.startswith('pzs3us1/00461/1/17/')}
    assert len(training)==398 and all(v['original']!=v['text'] for v in training.values())
    assert all(re.findall('<PAD=[^>]*>',v['original'])==re.findall('<PAD=[^>]*>',v['text']) for v in training.values())
    baseui=json.loads((ROOT/'cn5-glyph-fix1-resources/game-text/translations/ui/zh-CN.json').read_text('utf-8'))['labels']
    assert set(baseui)==set(ui) and all(ui[k]['original']==v['original'] for k,v in baseui.items())
    art=json.loads((RES/'game-text/translations/labels/zh-CN.json').read_text('utf-8'))['labels']
    protected=[k for k in art if k.startswith(('notice-','combo-','timer-','win-counter','blast-stock-counter'))]
    assert all(art[k]['original']==art[k]['text'] for k in protected)
    for before_file in (ROOT/'cn5-glyph-fix1-resources/game-text/art').rglob('*.bin'):
        assert before_file.read_bytes()==(RES/'game-text/art'/before_file.relative_to(ROOT/'cn5-glyph-fix1-resources/game-text/art')).read_bytes()
    missing_shapes=[hex(c) for c in required if original[c].getchannel('A').getbbox() is None
                    and not chr(c).isspace() and not identities.get(c,'x').isspace()]
    assert not missing_shapes,missing_shapes
    canvases=[]
    for _,_,key,_ in SAMPLES:
        text=ui[key]['text'];width=350*4; canvas=Image.new('RGBA',(width,140*4))
        for row,line in enumerate(text.split('\n')):
            x=12*4
            for ch in line:
                code=ord(ch)
                if code in rendered:
                    glyph,advance,top=rendered[code];canvas.alpha_composite(glyph,(x,40+row*23*4-top*4))
                else:
                    glyph=original[code];advance=glyph.width
                    canvas.alpha_composite(glyph.resize((glyph.width*4,glyph.height*4),Image.Resampling.NEAREST),(x,40+row*23*4))
                x+=advance*4
        bg=Image.new('RGB',(1000,320),'#123c69');label=ImageDraw.Draw(bg)
        label.text((12,8),key,font=ImageFont.truetype(r'C:\Windows\Fonts\msyh.ttc',16),fill='white')
        canvas.thumbnail((980,280));bg.paste(canvas,(10,32),canvas);canvases.append(bg)
    proof=Image.new('RGB',(1000,320*len(canvases)))
    for i,im in enumerate(canvases):proof.paste(im,(0,i*320))
    proof.save(OUT/'native-body-preview.png')
    report={'catalog_rows':len(ui),'catalog_IDs_and_originals_unchanged':True,'training_rows':len(training),
            'training_PAD_tags_unchanged':True,'font_cells':len(original),'missing_glyphs':0,
            'native_vector_glyphs_rendered':len(rendered),'ambiguous_PUA_cells_keep_original_pixels':fallback,
            'original_US_fonts_and_boot_nonfont_members_byte_identical':True,'protected_battle_labels':len(protected),
            'art_bank_byte_identical':True,'native_font_file_check':'passed','game_launched':False,
            'visual_validation':'Offline native renderer only; in-game placement needs user verification.'}
    (OUT/'resource-checks.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n','utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
