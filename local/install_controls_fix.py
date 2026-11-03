"""Install only reviewed runtime files, with backups and complete personal-data checks."""
from pathlib import Path
from datetime import datetime
import hashlib
import json
import os
import shutil
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]
DEST = Path(r'E:\PS2 yizhi\Tenkaichi3Decomp')
RECORDS = ROOT / 'records'
QA = ROOT / 'port/build/qa-local/Tenkaichi3Decomp'

def sha(path):
    return hashlib.file_digest(path.open('rb'), 'sha256').hexdigest()

def personal():
    result = {}
    for directory, dirs, files in os.walk(DEST):
        for name in files:
            path = Path(directory) / name
            rel = path.relative_to(DEST).as_posix()
            if rel in {'bt3_settings.txt', 'bt3_wii_controls.ini'} or rel.startswith(('saves/', 'wii_profiles/')):
                result[rel] = sha(path)
    return result

def main():
    assert DEST.resolve() == Path(r'E:\PS2 yizhi\Tenkaichi3Decomp').resolve() and DEST.is_dir()
    validation = json.loads((RECORDS / 'validation.json').read_text(encoding='utf-8'))
    assert validation['ui_verified'] and all(v['passed'] for v in validation['suites'].values())
    assert validation['network_source_and_objects']['protocol'] == 5
    history = json.loads((RECORDS / 'code-history/source-deltas.json').read_text(encoding='utf-8'))
    assert all(p['patch_applied_and_all_source_verified'] for p in history['patches'].values())
    # Refuse to replace an executable that the user currently has open.
    command = "Get-CimInstance Win32_Process -Filter \"Name='Tenkaichi3Decomp.exe'\" | Select-Object -ExpandProperty ExecutablePath"
    running = subprocess.check_output(['powershell.exe', '-NoProfile', '-Command', command], text=True, errors='replace')
    assert str(DEST / 'Tenkaichi3Decomp.exe').casefold() not in running.casefold(), 'Close the installed game before replacing it'
    release = json.loads((RECORDS / 'official-release.json').read_text(encoding='utf-8'))
    asset = next(a for a in release['assets'] if a['name'] == 'Tenkaichi3Decomp-windows-x64.zip')
    assert 'sha256:' + sha(ROOT / 'port/build/upstream-0.1.38.9-windows-x64.zip') == asset['digest']
    files = {name: QA / name for name in ['Tenkaichi3Decomp.exe', 'Tenkaichi3Decomp.exe.mem', 'Tenkaichi3Decomp.dat', 'SDL3.dll']}
    files.update({'Wii-Local-r11-说明.md': ROOT / 'local/CONTROLS_FIX_CHANGES.md',
                  'licenses/zlib.txt': ROOT / 'port/third_party/zlib/LICENSE',
                  'licenses/dolphin.txt': ROOT / 'port/third_party/dolphin/license.txt'})
    stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    backup = RECORDS / ('installed-backup-' + stamp)
    backup.mkdir()
    before_personal = personal()
    before = {}
    # Back up every replacement before writing any of them.
    for name in files:
        target = DEST / name
        before[name] = sha(target) if target.is_file() else None
        if target.is_file():
            saved = backup / name; saved.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(target, saved)
    replaced = []
    try:
        for name, source in files.items():
            assert source.is_file(), source
            target = DEST / name; target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target); replaced.append(name)
            assert sha(source) == sha(target), name
    except Exception:
        for name in replaced:
            target = DEST / name
            if before[name] is not None:
                shutil.copy2(backup / name, target)
            elif target.is_file():
                target.unlink()
        raise
    assert personal() == before_personal, 'Personal files changed unexpectedly'
    report = {'edition': 'r11-ControlsFix-W3', 'share_code_format': 'BT3W3', 'official_version': '0.1.38.9',
              'official_commit': validation['official_commit'], 'destination': str(DEST),
              'backup': str(backup), 'before': before,
              'after': {name: sha(DEST / name) for name in files},
              'personal_files_unchanged': True, 'personal_hashes': before_personal,
              'game_resources_and_other_unlisted_files_not_written': True,
              'no_commits_pushes_or_PR_updates': True, 'remote_UU_test': 'not performed'}
    manifest = json.dumps(report, ensure_ascii=False, indent=2) + '\n'
    (RECORDS / 'deployment.json').write_text(manifest, encoding='utf-8')
    (DEST / 'Wii-Local-r11-Build.json').write_text(manifest, encoding='utf-8')
    print('Installed r11-W3 on official 0.1.38.9:', DEST)
    print('Backed up replaced files:', backup)
    print('Verified unchanged personal files:', len(before_personal))

if __name__ == '__main__':
    main()
