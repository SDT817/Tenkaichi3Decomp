"""Three-way merge the installed CN7-I source onto the requested official tag."""
from pathlib import Path
import hashlib
import io
import json
import os
import subprocess
import tarfile
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
OLD = ROOT.parent / 'Tenkaichi3Decomp-WiiLocal-r8-CN7-ImmediateI'
BASE = '52b675c3ee4ed90f4f0d8e94217867a52638cc15'
UPSTREAM = '6a8d1429e6b71618107d945aeb10c56f1cd7cc1c'
RECORDS = ROOT / 'records'

def git(*args, cwd=ROOT):
    return subprocess.check_output(['git', '-c', 'core.safecrlf=false', *args], cwd=cwd)

def snapshot(commit):
    with tarfile.open(fileobj=io.BytesIO(git('archive', commit))) as archive:
        return {m.name: normalized(archive.extractfile(m).read()) for m in archive if m.isfile()}

def normalized(data):
    try:
        if b'\0' not in data:
            data.decode('utf-8')
            return data.replace(b'\r\n', b'\n')
    except UnicodeDecodeError:
        pass
    return data

def previous():
    result = {}
    for directory, dirs, files in os.walk(OLD):
        dirs[:] = [d for d in dirs if d not in {'.git', '__pycache__', 'build', 'build_release', 'dist', 'records', 'gamedata', 'saves'}]
        for name in files:
            path = Path(directory) / name
            result[path.relative_to(OLD).as_posix()] = normalized(path.read_bytes())
    return result

def archive(path, files):
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for name, data in sorted(files.items()):
            z.writestr('source/' + name, data)

def main():
    assert git('rev-parse', 'HEAD').decode().strip() == UPSTREAM
    assert not (ROOT / 'port/src/gs/control_bindings.cpp').exists(), 'Use a fresh official checkout'
    RECORDS.mkdir(exist_ok=True)
    ancestor, official, old = snapshot(BASE), snapshot(UPSTREAM), previous()
    for name, data in official.items():
        (ROOT / name).write_bytes(data)
    archive(RECORDS / 'previous-CN7-I-source.zip', old)
    archive(RECORDS / 'official-0.1.38.9-source.zip', official)
    results = {}
    for name in sorted(ancestor.keys() | old.keys()):
        if old.get(name) == ancestor.get(name):
            continue
        target = ROOT / name
        if name not in old:
            raise RuntimeError('Unexpected old deletion: ' + name)
        local = old[name]
        target.parent.mkdir(parents=True, exist_ok=True)
        if name in ancestor and name in official:
            with tempfile.TemporaryDirectory(prefix='bt3-controls-merge-') as temp:
                paths = [Path(temp) / p for p in ('local', 'ancestor', 'official')]
                for path, data in zip(paths, (local, ancestor[name], official[name])):
                    path.write_bytes(data)
                merged = subprocess.run(['git', 'merge-file', '-p', *map(str, paths)], capture_output=True)
                assert 0 <= merged.returncode <= 127, merged.stderr
                target.write_bytes(merged.stdout)
                results[name] = {'conflicts': merged.returncode}
        else:
            assert name not in official, name
            target.write_bytes(local)
            results[name] = {'addition': True}
    report = {'previous_official_base': BASE, 'official_base': UPSTREAM, 'files': results,
              'previous_source_sha256': hashlib.sha256((RECORDS / 'previous-CN7-I-source.zip').read_bytes()).hexdigest()}
    (RECORDS / 'merge.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: v for k, v in results.items() if v.get('conflicts')}, indent=2))
    print('Merged', len(results), 'local files; previous source archived.')

if __name__ == '__main__':
    main()
