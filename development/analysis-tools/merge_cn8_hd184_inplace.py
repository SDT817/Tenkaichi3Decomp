"""Restore the approved HD184 registration and verify assets in the existing CN8 folder.

No gamedata tree is copied; only genuinely different runtime files are written.
The original CN8 records remain the before endpoint, with an incremental repair.
"""
from pathlib import Path
import hashlib
import json
import re
import sys
import zipfile

import record_cn8_history as history
from prepare_cn8_source import ROOT, OUT, NEW

GAME = OUT/'Test-CN8-Official1391-MenuCache/Tenkaichi3Decomp'
HD = ROOT/'cn7-hd184-records'
FIX = OUT/'records/hd184-inplace-fix-20261029'
SOURCE_MANIFEST = 'port/third_party/fonts/fonts.tsv'


def file_hash(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f,'sha256').hexdigest()


def main():
    assert not (FIX/'merge-result.json').exists(), 'Repair already completed; preserve the result'
    FIX.mkdir(exist_ok=True)
    before = {'fonts/fonts.tsv':(GAME/'fonts/fonts.tsv').read_bytes(),
              'bt3_settings.txt':(GAME/'bt3_settings.txt').read_bytes()}
    history.archive(FIX/'original-game-config.zip',before)
    source_before = {SOURCE_MANIFEST:(NEW/SOURCE_MANIFEST).read_bytes()}
    history.archive(FIX/'source-before.zip',source_before)
    programs = {n:file_hash(GAME/n) for n in ('Tenkaichi3Decomp.exe','Tenkaichi3Decomp.exe.mem',
                                           'Tenkaichi3Decomp.dat','SDL3.dll')}
    personal = {}
    for name in ('saves','wii_profiles'):
        for p in (GAME/name).rglob('*'):
            if p.is_file():personal[p.relative_to(GAME).as_posix()]=file_hash(p)
    personal['bt3_wii_controls.ini']=file_hash(GAME/'bt3_wii_controls.ini')
    approved = {}
    with zipfile.ZipFile(HD/'CN7-HD184-complete-resources.zip') as z:
        assert z.testzip() is None
        rows=[n for n in z.read('fonts/fonts.tsv').decode('utf-8-sig').splitlines()
              if n.startswith('bt3cn-rounded-bold.ttf\t')]
        assert len(rows)==1 and rows[0].split('\t')[2]=='3'
        for n in z.namelist():
            if n.endswith('/') or not n.startswith(('fonts/','game-text/','mods/')):continue
            if n=='game-text/translations/ui/en.json':continue
            dest=n if n.startswith('fonts/') else 'gamedata/'+n
            approved[dest]=z.read(n)
    catalog=source_before[SOURCE_MANIFEST]
    assert b'bt3cn-rounded-bold.ttf\t' not in catalog
    catalog=catalog.rstrip(b'\r\n')+b'\n'+rows[0].encode('utf-8')+b'\n'
    approved['fonts/fonts.tsv']=catalog
    # No source recompile is needed: this manifest is read at run time.
    (NEW/SOURCE_MANIFEST).write_bytes(catalog)
    changed=[];backups=dict(before)
    for n,data in approved.items():
        p=GAME/n
        assert p.is_file(), 'Unexpected missing resource: '+n
        if p.read_bytes()!=data:
            backups[n]=p.read_bytes();p.write_bytes(data);changed.append(n)
        assert file_hash(p)==history.sha(data)
    settings=before['bt3_settings.txt']
    # Use the approved Chinese locale by default for direct EXE starts as well
    # as the existing Chinese launcher. Preserve every unrelated setting byte.
    for key,value in [(b'menu_lang',b'"zh-CN"'),(b'language_prompt_always',b'0')]:
        settings,count=re.subn(rb'(?m)^'+key+rb'=[^\r\n]*',key+b'='+value,settings)
        assert count==1,key
    (GAME/'bt3_settings.txt').write_bytes(settings)
    if settings!=before['bt3_settings.txt']:changed.append('bt3_settings.txt')
    for key in ('menu_font_id','text_font_id'):
        assert re.search(rb'(?m)^'+key.encode()+rb'=831785631\r?$',settings)
    history.archive(FIX/'replaced-game-files-before.zip',backups)
    history.RECORDS=FIX
    patch=history.save_patch('CN8-to-HD184-font-registration.patch',source_before,{SOURCE_MANIFEST:catalog})
    history.archive(FIX/'runtime-config-after.zip',{'fonts/fonts.tsv':catalog,'bt3_settings.txt':settings})
    assert all(file_hash(GAME/n)==h for n,h in programs.items())
    assert all(file_hash(GAME/n)==h for n,h in personal.items())
    # The only gamedata candidates were existing approved HD184 resources.
    # In this installation their contents already agree, so none is rewritten.
    report={'edition':'CN8-HD184-registration-fix','date':'2026-10-29',
            'game_path':str(GAME),'official_version':'0.1.39.1',
            'cause':'Chinese TTF was present but missing from fonts.tsv; its saved id resolved to Original',
            'HD184_archive_sha256':file_hash(HD/'CN7-HD184-complete-resources.zip'),
            'approved_runtime_resources':{n:history.sha(b) for n,b in approved.items()},
            'updated_game_files':changed,'new_gamedata_copy_created':False,
            'gamedata_files_written':[n for n in changed if n.startswith('gamedata/')],
            'source_changed':[SOURCE_MANIFEST],'source_patch':patch,
            'code_or_program_recompiled':False,'programs_unchanged':programs,
            'saves_profiles_controls_unchanged':personal,
            'only_setting_keys_changed':['menu_lang','language_prompt_always'],
            'game_launched':False,'gameplay_verification':'pending user'}
    history.write(FIX/'merge-result.json',report)
    history.write(FIX/'source-after-sha256.json',history.hashes(history.source_endpoint(NEW)))
    for name in ('merge_cn8_hd184_inplace.py','package_cn8_test.py'):
        (FIX/name).write_bytes((ROOT/'tools'/name).read_bytes())
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
