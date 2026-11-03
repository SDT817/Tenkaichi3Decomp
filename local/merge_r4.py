"""Reproduce the r4 -> official 0.1.38.1 merge without touching r4."""
from pathlib import Path
import json
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
OLD = ROOT.parent / 'Tenkaichi3Decomp-WiiLocal-r4'
BASE = 'aec1f8af41c50c293d4b7daecdb0b8ba97ff512f'
UPSTREAM = '11059a6d3e814cf36e6ca1f6307839f61c56f1cc'

def git(*args, cwd=ROOT):
    return subprocess.check_output(['git', '-c', 'core.safecrlf=false', *args], cwd=cwd)

def main():
    assert not (ROOT / 'port/src/gs/control_profiles.cpp').exists(), 'Use only in a clean official checkout'
    assert git('rev-parse', 'HEAD').decode().strip() == UPSTREAM
    files = set(git('ls-tree', '-rz', '--name-only', UPSTREAM).decode().split('\0'))
    results = {}
    for name in filter(None, git('diff', '--name-only', '-z', BASE, cwd=OLD).decode().split('\0')):
        source, target = OLD / name, ROOT / name
        assert source.is_file(), name
        local = source.read_bytes().replace(b'\r\n', b'\n')
        target.parent.mkdir(parents=True, exist_ok=True)
        if name in files:
            with tempfile.TemporaryDirectory(prefix='bt3-r5-merge-') as temp:
                paths = [Path(temp) / p for p in ('local', 'ancestor', 'official')]
                for path, data in zip(paths, (local, git('show', f'{BASE}:{name}', cwd=OLD), git('show', f'{UPSTREAM}:{name}'))):
                    path.write_bytes(data)
                merge = subprocess.run(['git', 'merge-file', '-p', *map(str, paths)], capture_output=True)
                assert 0 <= merge.returncode <= 127, merge.stderr
                target.write_bytes(merge.stdout)
                results[name] = f'{merge.returncode} conflict(s)'
        else:
            target.write_bytes(local)
            results[name] = 'local addition'
    (ROOT / 'local/merge-r4-results.json').write_text(json.dumps(results, indent=2) + '\n')
    print(json.dumps(results, indent=2))

if __name__ == '__main__': main()
