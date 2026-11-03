"""Fix the existing small update archives and add a final repair manifest."""
from pathlib import Path
import json
import os
import re
import zipfile

from merge_cn8_hd184_inplace import ROOT, OUT, NEW, GAME, FIX, file_hash
from record_cn8_history import load_zip, sha, write, hashes, source_endpoint


def replace_zip(path, changes):
    prior=file_hash(path)
    temporary=path.with_suffix('.hd184-tmp.zip')
    assert not temporary.exists(),temporary
    with zipfile.ZipFile(path) as old,zipfile.ZipFile(temporary,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as new:
        assert old.testzip() is None
        names=set(old.namelist())
        for item in old.infolist():
            if item.is_dir():continue
            new.writestr(item.filename,changes.get(item.filename,old.read(item.filename)))
        for name,data in changes.items():
            if name not in names:new.writestr(name,data)
    with zipfile.ZipFile(temporary) as z:
        assert z.testzip() is None
        assert len(z.namelist())==len(set(z.namelist()))
        for n,b in changes.items():assert z.read(n)==b
    os.replace(temporary,path)
    return {'before':prior,'after':file_hash(path),'bytes':path.stat().st_size,'changed_entries':sorted(changes)}


def main():
    result=json.loads((FIX/'merge-result.json').read_text('utf-8'))
    native=json.loads((FIX/'deployed-font-verification.json').read_text('utf-8'))
    assert native['before']['menu_falls_back_to_original'] and native['after']['passed']
    assert result['gamedata_files_written']==[] and not result['new_gamedata_copy_created']
    assert all(file_hash(GAME/n)==h for n,h in result['approved_runtime_resources'].items())
    assert all(file_hash(GAME/n)==h for n,h in result['programs_unchanged'].items())
    assert all(file_hash(GAME/n)==h for n,h in result['saves_profiles_controls_unchanged'].items())
    backup=load_zip(FIX/'original-game-config.zip')['bt3_settings.txt']
    current=(GAME/'bt3_settings.txt').read_bytes()
    remove=lambda b:re.sub(rb'(?m)^(menu_lang|language_prompt_always)=[^\r\n]*',b'',b)
    assert remove(backup)==remove(current),'Unrelated setting changed'
    catalog=(GAME/'fonts/fonts.tsv').read_bytes()
    assert catalog==(NEW/'port/third_party/fonts/fonts.tsv').read_bytes()
    records=OUT/'records'
    deployment=json.loads((OUT/'verification/deployment.json').read_text('utf-8'))
    deployment['HD184_registration_fix']={'record':str(FIX),'native_font_selection_passed':True,
        'font_manifest_sha256':sha(catalog),'new_gamedata_copy_created':False}
    deployment['resources_unchanged'].pop('fonts/fonts.tsv',None)
    deployment['personal_files_identical'].pop('bt3_settings.txt',None)
    deployment['settings_values_changed']=True
    deployment['only_setting_keys_changed']=result['only_setting_keys_changed']
    write(OUT/'verification/deployment-HD184-inplace.json',deployment)
    write(GAME/'CN8-Build.json',deployment)
    note=(FIX/'README-高清合并修复.md').read_bytes()
    (GAME/'CN8-HD184-修复说明.md').write_bytes(note)
    archived={}
    resource_zip=records/'CN8-complete-Chinese-resources.zip'
    archived[resource_zip.name]=replace_zip(resource_zip,{'fonts/fonts.tsv':catalog})
    resource_hashes=json.loads((records/'CN8-complete-Chinese-resources-sha256.json').read_text('utf-8'))
    resource_hashes['fonts/fonts.tsv']=sha(catalog)
    write(records/'CN8-complete-Chinese-resources-sha256.json',resource_hashes)
    update=OUT/'CN8-Official1391-Chinese-Wii-MenuCache-update.zip'
    with zipfile.ZipFile(update) as z:version=json.loads(z.read('CN8-version.json'))
    version['HD184_font_registry_fixed']=True
    patch={'fonts/fonts.tsv':catalog,'CN8-HD184-修复说明.md':note,
           'CN8-version.json':json.dumps(version,ensure_ascii=False,indent=2).encode('utf-8')+b'\n'}
    archived[update.name]=replace_zip(update,patch)
    update_hashes=json.loads((records/'update-package-files-sha256.json').read_text('utf-8'))
    update_hashes.update({n:sha(b) for n,b in patch.items()})
    write(records/'update-package-files-sha256.json',update_hashes)
    write(FIX/'updated-archive-hashes.json',archived)
    # Keep the original complete-source/patch records immutable; record this
    # one-line source-resource delta after that endpoint rather than duplicating it.
    assert hashes(source_endpoint(NEW))==json.loads((FIX/'source-after-sha256.json').read_text('utf-8'))
    original=load_zip(records/'final-r14-CN8-source.zip')
    current_source=source_endpoint(NEW)
    changed=[n for n in original.keys()|current_source.keys() if original.get(n)!=current_source.get(n)]
    assert changed==['port/third_party/fonts/fonts.tsv'],changed
    for name in ('finalize_cn8_hd184_inplace.py','package_cn8_test.py'):
        (FIX/name).write_bytes((ROOT/'tools'/name).read_bytes())
    main_readme=records/'README-代码修改记录.md'
    text=main_readme.read_text('utf-8')
    text+='''

## 2026-10-29 后续：CN7-HD184 字体注册修复

当前可玩目录已原位合入 `cn7-hd184-records` 的高清字体注册。原始四份补丁/完整源码包保留此次修复前端点；还原后再应用 `hd184-inplace-fix-20261029/CN8-to-HD184-font-registration.patch`。本次只新增源码字体清单的一行，不改 C/C++ 或配套程序。打包脚本和已有更新包也已修复，未复制新的 gamedata。当前资源与实际加载验证见该目录的 `README-高清合并修复.md`、`merge-result.json`、`deployed-font-verification.json`，当前源码指纹见 `source-after-sha256.json`。
'''
    main_readme.write_text(text,'utf-8')
    inventory={}
    for p in sorted(records.rglob('*')):
        if p.is_file() and p.name!='artifact-sha256.json':
            inventory[p.relative_to(OUT).as_posix()]={'bytes':p.stat().st_size,'sha256':file_hash(p)}
    inventory[update.name]={'bytes':update.stat().st_size,'sha256':file_hash(update)}
    write(records/'artifact-sha256.json',inventory)
    print('In-place HD184 merge verified; changed game files:',result['updated_game_files'])
    print('No gamedata written or copied. All programs and controls unchanged.')
    print('Existing resource/update ZIPs corrected, source delta replay verified.')
    print('Native deployed font selection/title rendering/main-menu prewarm check passed.')
    print('Record:',FIX/'README-高清合并修复.md')


if __name__=='__main__':main()
