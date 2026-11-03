"""Keep restorable source endpoints/patches, without making any commits."""
from pathlib import Path
import hashlib
import json
import os
import subprocess
import tempfile
import zipfile
from merge_controls_fix import ROOT, RECORDS, UPSTREAM, snapshot, normalized, archive, git

def sha(data):
    return hashlib.sha256(data).hexdigest()

def current_source():
    result = {}
    for directory, dirs, files in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in {'.git', '__pycache__', 'build', 'build_release', 'dist', 'records', 'gamedata', 'saves'}]
        for name in files:
            path = Path(directory) / name
            result[path.relative_to(ROOT).as_posix()] = normalized(path.read_bytes())
    return result

def patch(old, current, output):
    with tempfile.TemporaryDirectory(prefix='bt3-source-history-') as temp:
        folder = Path(temp)
        def run(*args):
            return subprocess.check_output(['git', '-c', 'core.autocrlf=false', '-c', 'core.safecrlf=false', *args], cwd=folder, stderr=subprocess.PIPE)
        def write(files):
            for name, data in files.items():
                target = folder / name; target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(data)
        run('init', '-q'); write(old); run('add', '-A'); ancestor = run('write-tree').decode().strip()
        for name in old.keys() - current.keys():
            (folder / name).unlink()
        write(current); run('add', '-A'); target = run('write-tree').decode().strip()
        data = run('diff-tree', '-r', '-p', '--full-index', '--binary', ancestor, target)
        output.write_bytes(data)
        per_file = output.parent / (output.stem + '-per-file')
        per_file.mkdir(exist_ok=True)
        changed = sorted(n for n in old.keys() | current.keys() if old.get(n) != current.get(n))
        for name in changed:
            file = per_file / (name + '.patch'); file.parent.mkdir(parents=True, exist_ok=True)
            file.write_bytes(run('diff-tree', '-r', '-p', '--full-index', '--binary', ancestor, target, '--', name))
        run('read-tree', '--reset', '-u', ancestor)
        run('apply', '--check', str(output.resolve()))
        run('apply', '--whitespace=nowarn', str(output.resolve()))
        actual = {p.relative_to(folder).as_posix(): p.read_bytes() for p in folder.rglob('*') if p.is_file() and '.git' not in p.relative_to(folder).parts}
        assert actual == current, 'Patch did not exactly restore the complete source'
        return {'sha256': sha(data), 'changed_files': changed, 'patch_applied_and_all_source_verified': True}

def main():
    out = RECORDS / 'code-history'; out.mkdir(exist_ok=True)
    current = current_source(); official = snapshot(UPSTREAM)
    previous_path = RECORDS / 'previous-CN7-I-source.zip'
    with zipfile.ZipFile(previous_path) as z:
        previous = {n.split('/', 1)[1]: normalized(z.read(n)) for n in z.namelist() if not n.endswith('/')}
    archive(out / 'r11-complete-source.zip', current)
    (out / 'official-original-git-source.zip').write_bytes(git('archive', '--format=zip', '--prefix=source/', UPSTREAM))
    report = {'official_version': '0.1.38.9', 'official_commit': UPSTREAM, 'edition': 'r11-ControlsFix',
              'text_normalization': 'LF; original official Git archive retained separately', 'commits_created': False,
              'previous_source_sha256': sha(previous_path.read_bytes()), 'patches': {}, 'files': []}
    for label, base in [('from-official-0.1.38.9', official), ('from-CN7-I-to-r11', previous)]:
        report['patches'][label] = patch(base, current, out / (label + '.patch'))
    for name in sorted(official.keys() | previous.keys() | current.keys()):
        if current.get(name) == official.get(name) == previous.get(name):
            continue
        report['files'].append({'path': name, 'official': sha(official[name]) if name in official else None,
                                'previous': sha(previous[name]) if name in previous else None,
                                'current': sha(current[name]) if name in current else None})
    (out / 'source-deltas.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('PASS: both complete patches applied and all source files verified; exact endpoints, per-file patches and hashes saved.')

if __name__ == '__main__':
    main()
