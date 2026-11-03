"""Merge the latest non-lobby local branch onto the verified official release."""
from pathlib import Path
import hashlib
import json
import shutil
import subprocess
import tempfile
import zipfile

from prepare_cn7_source import source_files

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'cn8-upstream-menu-cache-20261029'
OLD = ROOT.parent / 'Tenkaichi3Decomp-WiiLocal-r11-ControlsFix'
NEW = ROOT.parent / 'Tenkaichi3Decomp-WiiLocal-r14-CN8-MenuCache'
OFFICIAL_ZIP = ROOT / 'official-0.1.39.1-font-performance-study-20261029/official-v0.1.39.1-source.zip'


def normalize(data):
    try:
        if b'\0' not in data:
            data.decode('utf-8')
            return data.replace(b'\r\n', b'\n')
    except UnicodeDecodeError:
        pass
    return data


def zip_files(path):
    with zipfile.ZipFile(path) as z:
        return {n.split('/', 1)[1]: normalize(z.read(n)) for n in z.namelist() if not n.endswith('/')}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    assert not NEW.exists(), 'Do not modify completed source endpoints'
    live = json.loads((OUT / 'verification/official-latest.json').read_text('utf-8'))
    assert live['location'].endswith('/v0.1.39.1') and live['commits'] == ['7b43a75bd8b0aeabcce0a22c45e1ad66162ac9d7']
    assert sha(OFFICIAL_ZIP.read_bytes()) == '748cf9d08ff71b6e9106ca07ff9f50b63421e9ac261d4c5d1e13d4b23525e7e7'
    ancestor = zip_files(OLD / 'records/official-0.1.38.9-source.zip')
    official = zip_files(OFFICIAL_ZIP)
    local = {n: normalize(b) for n, b in source_files(OLD).items()
             if not n.startswith(('records/', 'build_release/'))}
    merged = dict(official)
    changes = {}
    for n in sorted(ancestor.keys() | local.keys()):
        if local.get(n) == ancestor.get(n):
            continue
        assert n in local, 'Unexpected local deletion: ' + n
        if n not in ancestor:
            assert n not in official, n
            merged[n] = local[n]
            changes[n] = {'addition': True}
        elif official.get(n) == ancestor[n]:
            merged[n] = local[n]
            changes[n] = {'conflicts': 0}
        else:
            assert n in official, n
            with tempfile.TemporaryDirectory(prefix='bt3-cn8-merge-') as t:
                paths = [Path(t) / p for p in ('local', 'ancestor', 'official')]
                for p, b in zip(paths, (local[n], ancestor[n], official[n])):
                    p.write_bytes(b)
                r = subprocess.run(['git', 'merge-file', '-p', *map(str, paths)], capture_output=True)
                assert 0 <= r.returncode <= 127, r.stderr
                merged[n] = r.stdout
                changes[n] = {'conflicts': r.returncode}
    for n, b in merged.items():
        p = NEW / n
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b)
    (OUT / 'records').mkdir(exist_ok=True)
    report = {'base': 'v0.1.39.1', 'commit': live['commits'][0], 'local_branch': OLD.name,
              'lobby_branch_included': False, 'files': changes,
              'official_sha256': {n: sha(b) for n, b in official.items()},
              'previous_sha256': {n: sha(b) for n, b in local.items()}}
    (OUT / 'records/initial-merge.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', 'utf-8')
    for name in ('gen', 'obj_data_win64'):
        shutil.copytree(OLD / 'port/build' / name, NEW / 'port/build' / name)
    print('Prepared', NEW)
    print('Conflicts:', {n: v for n, v in changes.items() if v.get('conflicts')})


if __name__ == '__main__':
    main()
