"""Save and apply-check the W3 incremental patch and complete baseline patches."""
import json
import zipfile
from save_controls_fix_history import current_source, patch, main as save_complete, sha
from merge_controls_fix import ROOT, archive

def main():
    out = ROOT / 'records/sharecode-w3-20261029'
    with zipfile.ZipFile(out / 'before-source.zip') as source:
        before = {name.split('/', 1)[1]: source.read(name) for name in source.namelist() if not name.endswith('/')}
    current = current_source()
    changed = sorted(name for name in before.keys() | current.keys() if before.get(name) != current.get(name))
    runtime = [name for name in changed if name.startswith(('port/', 'src/'))]
    assert runtime == ['port/src/gs/control_bindings.cpp', 'port/src/gs/control_bindings.h', 'port/src/gs/control_profiles.cpp'], runtime
    archive(out / 'after-source.zip', current)
    delta = patch(before, current, out / 'from-r11-to-r11-W3.patch')
    save_complete()
    report = {'edition': 'r11-ControlsFix-W3', 'official_version': '0.1.38.9',
              'commits_created': False, 'runtime_changed': runtime, 'patch': delta,
              'files': [{'path': name, 'before_sha256': sha(before[name]) if name in before else None,
                         'after_sha256': sha(current[name]) if name in current else None} for name in changed]}
    (out / 'source-deltas.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('PASS: W3 incremental patch and full official patches reproduce every source file; only 3 runtime files changed.')

if __name__ == '__main__':
    main()
