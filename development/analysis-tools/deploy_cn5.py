"""Prepare and verify a reviewable update, then install only its explicit files.

Default mode only writes the workspace. --deploy writes the user-requested
installation after preserving every replaced file; no game process is launched.
"""
from pathlib import Path
import argparse,csv,hashlib,io,json,os,re,shutil,subprocess,tempfile,zipfile
from merge_cn5_source import ROOT,NEW,UP

DEST=Path(r'E:\PS2 yizhi\Tenkaichi3Decomp')
STAGE=ROOT/'CN5-Update/Tenkaichi3Decomp'
RECORDS=ROOT/'cn5-records'
OUT=ROOT/'cn5-verification'
PLAN=RECORDS/'deployment-plan.json'
FONT_SETTINGS={'menu_font_id':'831785631','text_font_id':'831785631',
               'battle_font_id':'0','menu_lang':'"zh-CN"'}

def sha(b):return hashlib.sha256(b).hexdigest()
def hashes(folder):
    return {p.relative_to(folder).as_posix():sha(p.read_bytes())
            for p in sorted(folder.rglob('*')) if p.is_file()}
def write_json(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n','utf-8')
def personal():
    result={}
    for name in ['saves','wii_profiles']:
        folder=DEST/name
        if folder.exists():
            result.update({name+'/'+n:h for n,h in hashes(folder).items()})
    for file in DEST.glob('bt3_wii_controls.ini*'):
        if file.is_file():result[file.name]=sha(file.read_bytes())
    return result
def require_closed():
    result=subprocess.run(['powershell','-NoProfile','-NonInteractive','-Command',
        "$p=Get-Process -Name Tenkaichi3Decomp,bt3 -ErrorAction SilentlyContinue; if ($p) { $p | Select-Object -ExpandProperty ProcessName }; exit 0"],
        capture_output=True,check=True)
    assert not result.stdout.strip(),'Close the game before installing'
def safe_target(name):
    path=DEST/name
    assert path.resolve().is_relative_to(DEST.resolve()),'Destination escapes requested installation: '+name
    return path
def settings_bytes(original):
    data=original.decode('utf-8-sig');newline='\r\n' if '\r\n' in data else '\n'
    for key,value in FONT_SETTINGS.items():
        pattern=r'(?m)^'+re.escape(key)+r'=[^\r\n]*'
        if re.search(pattern,data):data=re.sub(pattern,key+'='+value,data)
        else:data+=('' if not data or data.endswith('\n') else newline)+key+'='+value+newline
    before=[line for line in original.decode('utf-8-sig').splitlines() if line.partition('=')[0] not in FONT_SETTINGS]
    after=[line for line in data.splitlines() if line.partition('=')[0] not in FONT_SETTINGS]
    assert before==after,'Unexpected personal setting change'
    return (b'\xef\xbb\xbf' if original.startswith(b'\xef\xbb\xbf') else b'')+data.encode('utf-8')
def atomic_copy(source,target):
    target.parent.mkdir(parents=True,exist_ok=True)
    handle,temp=tempfile.mkstemp(prefix='.cn5-',dir=target.parent);os.close(handle)
    try:
        shutil.copy2(source,temp);os.replace(temp,target)
    finally:
        if os.path.exists(temp):os.unlink(temp)

def prepare():
    assert not STAGE.exists(),'Keep the prepared stage immutable'
    assert DEST.is_dir() and (DEST/'gamedata/disc/SLUS_216.78').is_file()
    assert not PLAN.exists()
    require_closed();STAGE.mkdir(parents=True)
    with zipfile.ZipFile(UP/'Tenkaichi3Decomp-windows-x64.zip') as archive:
        for info in archive.infolist():
            if info.is_dir():continue
            name=info.filename.split('/',1)[1]
            target=STAGE/name;assert target.resolve().is_relative_to(STAGE.resolve())
            target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(archive.read(info))
    # GNU tools receive an ASCII-relative output path from the source directory.
    stripped=NEW/'port/build/cn5-release.exe'
    subprocess.run([r'E:\BT3-Wii-tools\mingw64\bin\strip.exe','--strip-all',
                    '-o','port/build/cn5-release.exe','port/build/bt3.exe'],cwd=NEW,check=True)
    for built,target in [('cn5-release.exe','Tenkaichi3Decomp.exe'),('bt3.dat','Tenkaichi3Decomp.dat'),
                         ('bt3.exe.mem','Tenkaichi3Decomp.exe.mem')]:
        shutil.copy2(NEW/'port/build'/built,STAGE/target)
    resources=ROOT/'cn5-resources'
    for name in ['fonts','mods','game-text']:
        target=STAGE/name if name=='fonts' else STAGE/'gamedata'/name
        shutil.copytree(resources/name,target,dirs_exist_ok=True)
    for source,target in [('port/third_party/dolphin/license.txt','dolphin-expression-gplv2.txt'),
                          ('port/third_party/dolphin/README.md','dolphin-expression-source.txt')]:
        shutil.copy2(NEW/source,STAGE/'licenses'/target)
    shutil.copy2(ROOT/'CN5-README.md',STAGE/'CN5-README.md')
    settings=DEST/'bt3_settings.txt';assert settings.is_file()
    (STAGE/settings.name).write_bytes(settings_bytes(settings.read_bytes()))
    core={n:sha((STAGE/n).read_bytes()) for n in ['Tenkaichi3Decomp.exe','Tenkaichi3Decomp.exe.mem','Tenkaichi3Decomp.dat']}
    write_json(STAGE/'CN5-Build.json',{'edition':'r6-CN5','official_version':'0.1.38.3',
       'official_commit':'13ecf4f3eaf4ba5b285adba33f81f699246598a9','protocol':5,
       'glyph_fix':{'E06F':'负'},'program_files':core,'game_launched':False})
    protected=personal();entries={}
    for name,new_hash in hashes(STAGE).items():
        target=safe_target(name);old_hash=sha(target.read_bytes()) if target.is_file() else None
        assert not target.exists() or target.is_file(),name
        entries[name]={'before':old_hash,'after':new_hash,
                       'action':'unchanged' if old_hash==new_hash else 'replace' if old_hash else 'add'}
    backup=RECORDS/'predeploy-backup';assert not backup.exists();backup.mkdir()
    for name,entry in entries.items():
        if entry['action']=='replace':
            path=backup/name;path.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(safe_target(name),path)
            assert sha(path.read_bytes())==entry['before']
    write_json(PLAN,{'target':str(DEST),'stage':str(STAGE),'entries':entries,
       'personal_files_before':protected,'settings_only_changed_keys':FONT_SETTINGS,
       'base_data_policy':'No disc, pzs3us0/1/2, install markers or executables from the original disc are written.',
       'game_launched':False})
    print('Prepared',len(entries),'explicit files;',sum(e['action']=='replace' for e in entries.values()),
          'replacements backed up;',sum(e['action']=='add' for e in entries.values()),'new files.')
    print('Stage:',STAGE);print('Plan:',PLAN)

def deploy():
    assert not (OUT/'deployment.json').exists(),'An already verified installation is immutable in these records'
    plan=json.loads(PLAN.read_text('utf-8'));assert plan['target']==str(DEST) and plan['stage']==str(STAGE)
    require_closed();assert personal()==plan['personal_files_before'],'Personal files changed since preparation'
    assert hashes(STAGE)=={n:e['after'] for n,e in plan['entries'].items()},'Prepared stage changed'
    for name,entry in plan['entries'].items():
        target=safe_target(name);current=sha(target.read_bytes()) if target.is_file() else None
        assert current==entry['before'],'Installation changed since preparation: '+name
    applied=[]
    try:
        for name,entry in plan['entries'].items():
            if entry['action']=='unchanged':continue
            atomic_copy(STAGE/name,safe_target(name));applied.append(name)
        for name,entry in plan['entries'].items():assert sha(safe_target(name).read_bytes())==entry['after'],name
        assert personal()==plan['personal_files_before'],'Personal data changed'
    except BaseException:
        for name in reversed(applied):
            entry=plan['entries'][name]
            if entry['before'] is None:safe_target(name).unlink()
            else:atomic_copy(RECORDS/'predeploy-backup'/name,safe_target(name))
        raise
    result={**plan,'status':'installed and verified','program_files':json.loads((STAGE/'CN5-Build.json').read_text('utf-8'))['program_files'],
       'personal_files_unchanged':True,'all_staged_files_verified':True,'actual_written_files':applied,
       'game_launched':False,'runtime_multiplayer_test':'not performed'}
    write_json(OUT/'deployment.json',result);write_json(RECORDS/'deployment.json',result)
    write_json(OUT/'user-data-checks.json',{'settings_other_lines_preserved':True,'settings_changed_keys':FONT_SETTINGS,
       'saves_Wii_profiles_and_bindings_unchanged':True,'personal_file_hashes':personal()})
    print('Installed and verified',len(applied),'files at',DEST)
    print('Saved games, Wii bindings, profiles and all other personal setting lines preserved.')

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--deploy',action='store_true')
    args=parser.parse_args();deploy() if args.deploy else prepare()
