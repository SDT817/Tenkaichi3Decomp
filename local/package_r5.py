"""Archive this edition, exact source history, and validation without commits."""
from pathlib import Path
import hashlib
import json
import shutil
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]
BASE = '11059a6d3e814cf36e6ca1f6307839f61c56f1cc'
NAME = 'Tenkaichi3Decomp-WiiLocal-r5'
DIST = ROOT / 'dist' / NAME
CORE = ('Tenkaichi3Decomp.exe', 'Tenkaichi3Decomp.dat', 'Tenkaichi3Decomp.exe.mem')

def git(*args):
    return subprocess.check_output(['git', '-c', 'core.safecrlf=false', *args], cwd=ROOT)

def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def archive(path, folder, prefix=''):
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as out:
        for file in sorted(folder.rglob('*')):
            if file.is_file(): out.write(file, prefix + file.relative_to(folder).as_posix())

def main():
    assert git('rev-parse', 'HEAD').decode().strip() == BASE
    assert not git('diff', '--cached', '--name-only').strip()
    git('diff', '--check', 'HEAD')
    assert not DIST.exists(), 'Keep old packages; use a new edition name'
    checks = json.loads((ROOT / 'port/build/r5-validation.json').read_text(encoding='utf-8'))
    assert checks['automated_checks_passed'] and checks['ui_verified']
    network = json.loads((ROOT / 'port/build/network-invariants.json').read_text())
    assert network['official_base'] == BASE and network['protocol'] == 5
    assert len(network['sources']) == 23 and len(network['objects_without_debug']) == 5
    netplay = {}
    for name in ('verify-local-r5-host-ps2', 'verify-local-r5-host-wii'):
        result = json.loads((ROOT / 'port/build' / name / 'result.json').read_text())
        assert all(v['character_select'] and v['fight_reached'] and not v['desync'] and
                   v['unexpected_exit_code'] is None and v['pad_frames'] > 10000 for v in result.values())
        netplay[name] = result
    DIST.mkdir(parents=True)
    out = DIST / NAME / 'Tenkaichi3Decomp'
    out.mkdir(parents=True)
    official = ROOT / 'port/build/upstream-0.1.38.1-windows-x64.zip'
    with zipfile.ZipFile(official) as source:
        for name in source.namelist():
            path = Path(name)
            assert path.parts[0] == 'Tenkaichi3Decomp' and '..' not in path.parts
            if not name.endswith('/'):
                target = out / Path(*path.parts[1:])
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(source.read(name))
    qa = ROOT / 'port/build/qa-local/Tenkaichi3Decomp'
    for name in CORE: shutil.copy2(qa / name, out / name)
    assert len((out / CORE[2]).read_text().splitlines()) > 2
    shutil.copy2(ROOT / 'local/Readme-r5-zh-CN.txt', out / 'Wii-Local-Readme-zh-CN.txt')
    for source, name in [('license.txt', 'dolphin-expression.txt'), ('README.md', 'dolphin-expression-source.md')]:
        shutil.copy2(ROOT / 'port/third_party/dolphin' / source, out / 'licenses' / name)
    records = DIST / 'records'
    records.mkdir()
    from save_code_history import save
    history = save(records)
    manifest = {
        'edition': 'r5', 'official_version': '0.1.38.1', 'official_commit': BASE,
        'official_archive_sha256': digest(official), 'branch': 'codex/wii-controls-r5',
        'commits_created': False, 'remote_updates': False, 'core_sha256': {name: digest(out / name) for name in CORE},
        'checks': checks, 'network_invariants': network, 'local_netplay': netplay,
        'remote_UU_test': 'Not performed for r5; remote validation remains a user test',
        'patches_applied_and_source_verified': history['patches_applied_and_source_verified'],
    }
    (records / 'build-and-validation.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    for name in ('CODE_CHANGES.md', '修改记录与更新说明.md', 'Readme-r5-zh-CN.txt', 'merge-r4-results.json'):
        shutil.copy2(ROOT / 'local' / name, records / name)
    shutil.copy2(ROOT / 'docs/local-wii-profiles.md', records / 'preset-format-and-dolphin.md')
    shutil.copy2(ROOT / 'port/build/r5-tests.json', records / 'automated-test-output.json')
    for title in ('combined-to-split', 'separated-to-combined', 'dolphin-list', 'net-host', 'net-join', 'net-quick', 'misc'):
        path = ROOT / 'port/build' / ('r5-final-' + title + '.png')
        shutil.copy2(path, records / path.name)
    full = DIST / (NAME + '-windows-x64.zip')
    archive(full, out, 'Tenkaichi3Decomp/')
    update = DIST / (NAME + '-update.zip')
    with zipfile.ZipFile(update, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for name in (*CORE, 'Wii-Local-Readme-zh-CN.txt', 'licenses/dolphin-expression.txt', 'licenses/dolphin-expression-source.md'):
            z.write(out / name, name)
    sources = [name for name in git('ls-files', '-z').decode().split('\0') if name and (ROOT / name).is_file()]
    source_zip = DIST / (NAME + '-source.zip')
    with zipfile.ZipFile(source_zip, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for name in sorted(set(sources)): z.write(ROOT / name, 'Tenkaichi3Decomp-source/' + name)
    record_zip = DIST / (NAME + '-records.zip')
    archive(record_zip, records)
    with zipfile.ZipFile(official) as original, zipfile.ZipFile(full) as final:
        for name in original.namelist():
            if name.endswith('/') or Path(name).name in CORE: continue
            assert original.read(name) == final.read(name), name
        for name in final.namelist():
            rel = Path(name).parts[1:]
            assert not rel or rel[0].lower() not in {'gamedata', 'saves', 'net_session', 'bt3_settings.txt', 'bt3_wii_controls.ini', 'wii_profiles'}
    for file in (full, update, source_zip, record_zip):
        with zipfile.ZipFile(file) as z: assert z.testzip() is None
        (DIST / (file.name + '.sha256')).write_text(digest(file) + '  ' + file.name + '\n')
        print(file, file.stat().st_size, flush=True)
    print('Packages, source restoration, official ancillary files and hashes verified.')

if __name__ == '__main__': main()
