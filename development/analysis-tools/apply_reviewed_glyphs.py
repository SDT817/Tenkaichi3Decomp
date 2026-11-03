"""Apply the user's completed glyph review as data, with exact local history.

No executable or game/network source is changed. Resource patches are applied
and reconstructed in isolated directories before exporting maintenance records.
"""
from pathlib import Path
from collections import Counter
import argparse,hashlib,json,os,shutil,subprocess,zipfile
from PIL import Image,ImageDraw,ImageFont
import build_cn4_resources as build
import build_cn3_resources as fonts
import render_cn_samples as iso_decoder
import save_cn3_records as history
import upstream_extract_eu_text as disc
from deploy_cn5 import DEST,personal,require_closed,atomic_copy,safe_target

ROOT=Path(__file__).resolve().parents[1]
INPUT=Path(r'E:\下载\BT3-字库修改表 (2).json')
BASE=ROOT/'cn5-glyph-fix1-resources'
RES=ROOT/'cn5-glyph-fix2-resources'
CHECK=ROOT/'cn5-glyph-fix2-verification'
OUT=ROOT/'cn5-glyph-fix2-records'
FONT='fonts/bt3cn-rounded-bold.ttf'
RUNTIME={FONT:FONT,'mods/pzs3us1/00004.bin':'gamedata/mods/pzs3us1/00004.bin'}

def sha(b):return hashlib.sha256(b).hexdigest()
def read(p):return json.loads(p.read_text('utf-8-sig'))
def write(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n','utf-8')
def resource_files(folder):return {p.relative_to(folder).as_posix():p.read_bytes() for p in sorted(folder.rglob('*')) if p.is_file()}
def validated():
    data=read(INPUT);index=read(ROOT/'glyph-review-20261023/records/全字库索引.json')
    rows={r['code']:r for r in index['rows']};mapping=read(BASE/'font-identities.json')
    assert data['format']=='BT3GlyphReview' and data['version']==1
    assert data['dataset']==index['id']=='CN5-G1-b734ad116bd9'
    assert data['resource_font_sha256']==index['fontHash']==sha((BASE/FONT).read_bytes())
    assert isinstance(data['changes'],list) and len(data['changes'])==96
    seen=set();fixes={};confirmed=[]
    _,coverage=fonts.cmap((BASE/FONT).read_bytes())
    for item in data['changes']:
        code=item['code'];assert code not in seen;seen.add(code)
        assert code in rows and item['kind']=='mapped' and item['status']=='wrong'
        assert item['current']==mapping[code]==rows[code]['identity']
        assert item['source_code']==rows[code]['rawCode'] and item['index']==rows[code]['index']
        value=item['corrected'];assert isinstance(value,str) and len(value)==1 and ord(value) in coverage
        assert not (0xd800<=ord(value)<=0xdfff or ord(value)<32 or 0xe000<=ord(value)<=0xf8ff)
        if value==mapping[code]:confirmed.append(item)
        else:fixes[code]=value
    assert len(fixes)==95 and len(confirmed)==1 and confirmed[0]['code']=='E68C'
    return data,fixes,confirmed

def make():
    data,fixes,confirmed=validated()
    assert not RES.exists() and not CHECK.exists(),'Preserve completed resource editions'
    CHECK.mkdir();shutil.copy2(INPUT,CHECK/'user-submitted-review.json')
    shutil.copytree(BASE,RES)
    iso_decoder.OUT=CHECK/'original-ISO-decoded';iso_decoder.OUT.mkdir()
    build.BASE=BASE;build.OUT=RES;build.GLYPH_FIXES=fixes;build.TOURNAMENT={}
    build.main()
    # No catalog edits are necessary: every usage keeps its original private code.
    catalog=read(RES/'game-text/translations/ui/zh-CN.json')['labels']
    corrections=read(RES/'glyph-corrections.json');unique=set();occurrences=0
    for item in corrections:
        character=chr(int(item['code'],16))
        ids=[key for key,row in catalog.items() if character in row['text']]
        item['affected_rows']=len(ids);item['sample_ids']=ids[:4];unique.update(ids)
        occurrences+=sum(row['text'].count(character) for row in catalog.values())
    write(CHECK/'corrections.json',corrections)
    manifest={'edition':'CN5-GlyphFix2','base':'CN5-GlyphFix1 / official 0.1.38.3',
       'submitted_entries':len(data['changes']),'actual_mapping_changes':len(fixes),
       'unchanged_confirmation':confirmed,'affected_unique_UI_rows':len(unique),'affected_character_occurrences':occurrences,
       'user_review_sha256':sha(INPUT.read_bytes()),'user_review_dataset':data['dataset'],
       'glyph_fixes':fixes,'source_of_truth':'User-completed glyph review; no additional OCR substitutions',
       'runtime_source_changes':False,'protocol':5}
    write(RES/'glyph-fix2-manifest.json',manifest);write(CHECK/'review-import-checks.json',manifest)
    script=(ROOT/'tools/verify_cn5_glyph_fix1_resources.py').read_text('utf-8')
    script=script.replace('cn5-glyph-fix1-resources','cn5-glyph-fix2-resources').replace('cn5-glyph-fix1-verification','cn5-glyph-fix2-verification')
    script=script.replace("ROOT/'cn5-resources", "ROOT/'cn5-glyph-fix1-resources")
    (ROOT/'tools/verify_cn5_glyph_fix2_resources.py').write_text(script,'utf-8')
    print('Built',len(fixes),'user-reviewed corrections; affected rows:',len(unique),'occurrences:',occurrences)

def atlas(folder):
    result={}
    for table in sorted(folder.glob('shared-*.tsv')):
        if table.name.endswith('.metrics.tsv'):continue
        lines=table.read_text('utf-8').splitlines();_,w,h=lines[0].split('\t')
        image=Image.frombytes('RGBA',(int(w),int(h)),table.with_suffix('.rgba').read_bytes())
        for line in lines[1:]:
            code,x,y,w,h,top,bottom=line.split('\t');x,y,w,h=map(int,(x,y,w,h))
            result[code]=(image.crop((x*4,y*4,(x+w)*4,(y+h)*4)),w,int(top),int(bottom))
    return result

def verify():
    data,fixes,confirmed=validated();assert sha((CHECK/'user-submitted-review.json').read_bytes())==sha(INPUT.read_bytes())
    old,new=read(BASE/'font-identities.json'),read(RES/'font-identities.json')
    assert {k:new[k] for k in new if new[k]!=old[k]}==fixes
    a,b=(BASE/FONT).read_bytes(),(RES/FONT).read_bytes();at,am=fonts.cmap(a);bt,bm=fonts.cmap(b)
    assert am.keys()==bm.keys() and {c for c in am if am[c]!=bm[c]}=={int(c,16) for c in fixes}
    for code,char in fixes.items():assert bm[int(code,16)]==bm[ord(char)]
    for tag,(off,size) in at.items():
        if tag in (b'cmap',b'head'):continue
        off2,size2=bt[tag];assert a[off:off+size]==b[off2:off2+size2]
    before,after=[disc.sections((p/'mods/pzs3us1/00004.bin').read_bytes()) for p in [BASE,RES]]
    assert before[:2]==after[:2] and before[7:]==after[7:]
    for p in (BASE/'game-text').rglob('*'):
        if p.is_file():assert p.read_bytes()==(RES/'game-text'/p.relative_to(BASE/'game-text')).read_bytes()
    previous,current=atlas(ROOT/'cn5-glyph-fix1-verification'),atlas(CHECK)
    assert previous.keys()==current.keys() and len(current)==2637
    changed=set()
    for code,(image,w,top,bottom) in current.items():
        was=previous[code]
        if (image.size,image.tobytes(),w,top,bottom)!=(was[0].size,was[0].tobytes(),*was[1:]):changed.add(code)
    assert changed==set(fixes),{'unexpected':sorted(changed-set(fixes)),'missing':sorted(set(fixes)-changed)}
    normalized=read(RES/'normalized-cells.json')
    metrics={}
    import csv
    for p in CHECK.glob('shared-*.rgba.metrics.tsv'):
        for row in csv.DictReader(p.open(),delimiter='\t'):metrics[row['code']]=row
    assert set(normalized)<=metrics.keys()
    assert len({(metrics[k]['scale'],metrics[k]['baseline'],metrics[k]['w'],metrics[k]['h']) for k in normalized})==1
    menu=CHECK/'menu-font';menu.mkdir(exist_ok=True)
    shutil.copy2(ROOT/'cn5-verification/menu-font/jobs.tsv',menu/'jobs.tsv')
    env=dict(os.environ);env['PATH']=r'E:\BT3-Wii-tools\mingw64\bin;'+env['PATH']
    run=subprocess.run(['tools/render_cn5_font.exe','cn5-glyph-fix2-resources/'+FONT,
       'cn5-glyph-fix2-verification/menu-font/jobs.tsv','cn5-glyph-fix2-verification/menu-font'],
       cwd=ROOT,env=env,capture_output=True,text=True,check=True)
    assert run.stdout.splitlines()==(ROOT/'cn5-verification/menu-font/rendered.tsv').read_text('utf-8').splitlines()
    (menu/'rendered.tsv').write_text(run.stdout,'utf-8')
    for i in range(320):assert (menu/f'{i:03d}.rgba').read_bytes()==(ROOT/'cn5-verification/menu-font'/f'{i:03d}.rgba').read_bytes()
    # Three contact sheets: original ISO at left and corrected native raster at right.
    import build_full_glyph_review as pictures
    pictures.NATIVE=CHECK;iso=pictures.originals();raw=read(RES/'font-code-map.json');inverse={v:int(k,16) for k,v in raw.items()}
    font=ImageFont.truetype(r'C:\Windows\Fonts\msyh.ttc',18);small=ImageFont.truetype(r'C:\Windows\Fonts\msyh.ttc',15)
    changes=read(CHECK/'corrections.json');pages=[]
    for start in range(0,len(changes),32):
        part=changes[start:start+32];canvas=Image.new('RGB',(1200,70+((len(part)+3)//4)*174),'#eef4fa');draw=ImageDraw.Draw(canvas)
        draw.text((15,10),f'已按校对表修正 · {start+1}–{start+len(part)} / {len(changes)}',font=font,fill='#17385e')
        draw.text((15,39),'左侧原汉化字形 / 右侧修正后的游戏实际渲染',font=small,fill='#617087')
        for i,item in enumerate(part):
            code=item['code'];x=(i%4)*300;y=70+(i//4)*174
            draw.rounded_rectangle((x+4,y+2,x+296,y+169),8,fill='white',outline='#d6e1ed')
            draw.text((x+12,y+8),code+'   '+item['before']+' → '+item['after'],font=font,fill='#1755a0')
            image=current[code][0].copy();image.putalpha(image.getchannel('A').point(lambda alpha:min(255,alpha*2)))
            pair=pictures.pair_picture(iso[inverse[code]],image.getchannel('A'),True)
            canvas.paste(pair,(x+46,y+39))
            draw.text((x+13,y+145),f"同步修正 {item['affected_rows']} 行",font=small,fill='#547264')
        path=CHECK/f'corrected-glyphs-{start//32+1:02d}.png';canvas.save(path);pages.append(path.name)
    result={'submitted_entries':96,'actual_glyph_changes':95,'unchanged_confirmation':['E68C'],
      'font_cmap_exact_changes':fixes,'outlines_metrics_and_other_mappings_unchanged':True,
      'native_rendered_codes':len(current),'native_unmodified_glyphs_exact':len(current)-len(changed),
      'native_menu_cells_identical_to_CN5':320,'normalized_fullwidth_cells':len(normalized),
      'common_scale_baseline_and_advance_preserved':True,'catalogs_menu_art_US_fonts_and_nonfont_boot_members_unchanged':True,
      'corrected_glyph_contact_sheets':pages,'runtime_source_changes':False,'protocol':5,'game_launched':False}
    write(CHECK/'changes-checks.json',result)
    print('PASS: 95 exact cmap/native glyph changes; 2542 other native glyphs and 320 menu cells identical.')

def prepare():
    data,fixes,confirmed=validated();assert (CHECK/'changes-checks.json').exists()
    assert not OUT.exists(),'Preserve completed records';require_closed();OUT.mkdir()
    plans={}
    for source,target in RUNTIME.items():
        current=safe_target(target);assert current.read_bytes()==(BASE/source).read_bytes(),'Installed resource differs: '+target
        backup=OUT/'predeploy-backup'/target;backup.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(current,backup)
        plans[target]={'source':str(RES/source),'before':sha(current.read_bytes()),'after':sha((RES/source).read_bytes())}
    metadata=DEST/'CN5-Build.json';meta=read(metadata);meta.update(glyph_review_update='CN5-GlyphFix2',
       completed_user_review={'records':96,'glyph_changes':95,'input_sha256':sha(INPUT.read_bytes())})
    meta['additional_glyph_fixes']={**meta.get('additional_glyph_fixes',{}),**fixes}
    meta['font_resources']={n:e['after'] for n,e in plans.items()}
    staged=OUT/'CN5-Build.json';write(staged,meta);shutil.copy2(metadata,OUT/'predeploy-backup/CN5-Build.json')
    plans['CN5-Build.json']={'source':str(staged),'before':sha(metadata.read_bytes()),'after':sha(staged.read_bytes())}
    protected={n:sha((DEST/n).read_bytes()) for n in ['Tenkaichi3Decomp.exe','Tenkaichi3Decomp.exe.mem','Tenkaichi3Decomp.dat','bt3_settings.txt']}
    write(OUT/'deployment-plan.json',{'target':str(DEST),'files':plans,'program_and_settings_before':protected,'personal_before':personal()})
    shutil.copy2(INPUT,OUT/'user-submitted-review.json')
    print('Prepared three files and predeployment backups; executable/settings/saves excluded.')

def deploy():
    assert not (OUT/'deployment.json').exists();require_closed()
    plan=read(OUT/'deployment-plan.json');assert plan['target']==str(DEST)
    assert personal()==plan['personal_before']
    for n,h in plan['program_and_settings_before'].items():assert sha((DEST/n).read_bytes())==h
    for n,e in plan['files'].items():assert sha(safe_target(n).read_bytes())==e['before'] and sha(Path(e['source']).read_bytes())==e['after']
    applied=[]
    try:
        for n,e in plan['files'].items():atomic_copy(Path(e['source']),safe_target(n));applied.append(n)
        for n,e in plan['files'].items():assert sha(safe_target(n).read_bytes())==e['after']
        assert personal()==plan['personal_before']
        for n,h in plan['program_and_settings_before'].items():assert sha((DEST/n).read_bytes())==h
    except BaseException:
        for n in reversed(applied):atomic_copy(OUT/'predeploy-backup'/n,safe_target(n))
        raise
    write(OUT/'deployment.json',{**plan,'status':'installed and verified','program_settings_and_personal_data_unchanged':True,'game_launched':False})
    print('Installed and verified all 95 user-reviewed corrections at',DEST)

def archive():
    assert (OUT/'deployment.json').exists() and not (OUT/'record-file-hashes.json').exists();history.OUT=OUT
    patches=[history.save_patch('GlyphFix1-to-GlyphFix2-resources.patch',resource_files(BASE),resource_files(RES))]
    history.save_directory_zip('GlyphFix2-complete-local-resources.zip',RES)
    prior={p.relative_to(ROOT/'cn5-glyph-fix1-records').as_posix():p.read_bytes() for p in sorted((ROOT/'cn5-glyph-fix1-records/tools').rglob('*')) if p.is_file()}
    tools={p.relative_to(ROOT).as_posix():p.read_bytes() for p in sorted((ROOT/'tools').iterdir())
       if p.is_file() and p.suffix in ('.py','.c','.cpp','.h','.ps1','.html','.cjs')}
    patches.append(history.save_patch('GlyphFix1-to-GlyphFix2-tools.patch',prior,tools))
    for n,b in tools.items():
        target=OUT/n;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(b)
    history.save_directory_zip('GlyphFix2-offline-verification.zip',CHECK)
    for name in ['corrections.json','review-import-checks.json','changes-checks.json','resource-checks.json']:
        shutil.copy2(CHECK/name,OUT/name)
    for p in CHECK.glob('corrected-glyphs-*.png'):shutil.copy2(p,OUT/p.name)
    write(OUT/'manifest.json',{'edition':'CN5-GlyphFix2','base':'CN5-GlyphFix1 / official 0.1.38.3',
       'completed_review_applied':True,'submitted_entries':96,'actual_glyph_changes':95,
       'unchanged_confirmation':'E68C 蜃→蜃','review_input_sha256':sha(INPUT.read_bytes()),
       'affected_unique_UI_rows':read(RES/'glyph-fix2-manifest.json')['affected_unique_UI_rows'],
       'actual_patches_reconstructed':patches,'runtime_source_changes':False,'protocol':5,
       'git_commits_created':False,'remote_updates':False,'game_launched':False,'predeploy_backup':'predeploy-backup/'})
    (OUT/'README.md').write_text('# CN5 用户全字库校对合入（2026-10-23）\n\n'
       '输入为用户提供的 BT3-字库修改表 (2).json，校验数据集、字体 SHA256、每项字码/原字/原始编码/索引。\n'
       '96 条记录中 95 处实际修正；E68C 蜃→蜃保留并记录为重复确认。按用户结果逐项应用，不额外猜测识别。\n'
       '运行资源仅更新 fonts/bt3cn-rounded-bold.ttf 与 gamedata/mods/pzs3us1/00004.bin，另更新构建记录。\n'
       '游戏程序、联机/协议、设置、存档、Wii 绑定和预设哈希保持不变；原文件已备份。\n'
       '原生 C 渲染逐码检查：95 处更正，其余 2542 个高清字形不变；320 个菜单单元不变。\n'
       '资源和工具包含实际可应用补丁，已在隔离目录应用后逐文件验证。保留完整资源、输入表、源码工具、渲染证据和哈希。\n'
       '既有源码与历史资源/记录不覆盖；没有创建提交、推送或更新 PR。本轮没有启动游戏。\n','utf-8')
    for p in OUT.glob('*.zip'):
        with zipfile.ZipFile(p) as z:assert z.testzip() is None
    write(OUT/'record-file-hashes.json',{p.relative_to(OUT).as_posix():sha(p.read_bytes()) for p in sorted(OUT.rglob('*')) if p.is_file()})
    bundle=ROOT/'CN5-GlyphFix2-user-reviewed-records.zip';assert not bundle.exists()
    with zipfile.ZipFile(bundle,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p in sorted(OUT.rglob('*')):
            if p.is_file():z.write(p,'cn5-glyph-fix2-records/'+p.relative_to(OUT).as_posix())
    with zipfile.ZipFile(bundle) as z:assert z.testzip() is None
    write(ROOT/'CN5-GlyphFix2-records-archive.json',{'file':bundle.name,'sha256':sha(bundle.read_bytes()),'ZIP_integrity':'passed'})
    print('Preserved full resources, real reconstructed patches, input review, verification and backups:',bundle)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['build','verify','prepare','deploy','archive']);args=p.parse_args()
    {'build':make,'verify':verify,'prepare':prepare,'deploy':deploy,'archive':archive}[args.mode]()
