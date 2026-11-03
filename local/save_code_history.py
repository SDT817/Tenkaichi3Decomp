"""Save exact source deltas and their bases without making a Git commit."""
from pathlib import Path
import hashlib
import io
import json
import shutil
import subprocess
import tarfile
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
BASE = '11059a6d3e814cf36e6ca1f6307839f61c56f1cc'
PREVIOUS_SOURCE = ROOT.parent / 'Tenkaichi3Decomp-WiiLocal-r4/dist/Tenkaichi3Decomp-WiiLocal-r4/Tenkaichi3Decomp-WiiLocal-r4-source.zip'


def git(*args, cwd=ROOT):
    return subprocess.check_output(['git', '-c', 'core.safecrlf=false', *args], cwd=cwd, stderr=subprocess.PIPE)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def normalize(data):
    if b'\0' in data:
        return data
    try:
        data.decode('utf-8')
    except UnicodeDecodeError:
        return data
    return data.replace(b'\r\n', b'\n')


def save(records):
    """Both patches are applied and compared byte-for-byte to their target source."""
    records = Path(records)
    history = records / 'code-history'
    history.mkdir(parents=True)
    files = [p for p in git('ls-files', '-z').decode().split('\0') if p and (ROOT / p).is_file()]
    current = {p: normalize((ROOT / p).read_bytes()) for p in files}
    changed = [p for p in git('diff', '--name-only', '-z', BASE).decode().split('\0') if p]
    patch = git('diff', '--full-index', '--binary', '--no-ext-diff', BASE, '--', '.')
    (history / 'from-official-0.1.38.1.patch').write_bytes(patch)
    per_file = history / 'per-file'
    per_file.mkdir()
    for path in changed:
        out = per_file / (path + '.patch')
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(git('diff', '--full-index', '--binary', '--no-ext-diff', BASE, '--', path))
    original = git('archive', '--format=zip', '--prefix=Tenkaichi3Decomp-source/', BASE)
    (history / 'official-0.1.38.1-source.zip').write_bytes(original)
    shutil.copy2(PREVIOUS_SOURCE, history / 'r4-source.zip')
    with zipfile.ZipFile(PREVIOUS_SOURCE) as z:
        previous = {n.split('/', 1)[1]: normalize(z.read(n)) for n in z.namelist() if not n.endswith('/')}
    # An isolated repository stores complete old/new blob IDs, without commits or
    # writes to the user's index. Its patch can also be checked against r4 alone.
    with tempfile.TemporaryDirectory(prefix='bt3-code-history-') as temp:
        folder = Path(temp)
        git('init', '-q', cwd=folder)
        git('config', 'core.autocrlf', 'false', cwd=folder)
        def write(snapshot):
            for path, data in snapshot.items():
                target = folder / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
        write(previous)
        git('add', '-A', cwd=folder)
        old_tree = git('write-tree', cwd=folder).decode().strip()
        for path in previous.keys() - current.keys():
            (folder / path).unlink()
        write(current)
        git('add', '-A', cwd=folder)
        new_tree = git('write-tree', cwd=folder).decode().strip()
        incremental = git('diff-tree', '-r', '-p', '--full-index', '--binary', old_tree, new_tree, cwd=folder)
        (history / 'from-r4-to-r5.patch').write_bytes(incremental)
        git('read-tree', '--reset', '-u', old_tree, cwd=folder)
        git('apply', '--check', str(history.resolve() / 'from-r4-to-r5.patch'), cwd=folder)
        git('apply', '--whitespace=nowarn', str(history.resolve() / 'from-r4-to-r5.patch'), cwd=folder)
        for path, data in current.items():
            assert (folder / path).read_bytes() == data, path
    with tempfile.TemporaryDirectory(prefix='bt3-official-patch-') as temp:
        folder = Path(temp)
        with tarfile.open(fileobj=io.BytesIO(git('archive', BASE))) as archive:
            archive.extractall(folder, filter='data')
        git('apply', '--check', str(history.resolve() / 'from-official-0.1.38.1.patch'), cwd=folder)
        git('apply', '--whitespace=nowarn', str(history.resolve() / 'from-official-0.1.38.1.patch'), cwd=folder)
        for path, data in current.items():
            assert normalize((folder / path).read_bytes()) == data, path
    manifest = {
        'official_base': BASE, 'official_version': '0.1.38.1', 'edition': 'r5',
        'r4_archive_sha256': sha(PREVIOUS_SOURCE.read_bytes()),
        'normalization': 'Text CRLF normalized to LF for patches and comparisons; original r4 archive retained verbatim',
        'patches_applied_and_source_verified': True, 'git_commits_created': False,
        'files': [],
    }
    for path in sorted(set(changed) | {p for p in previous.keys() | current.keys() if previous.get(p) != current.get(p)}):
        official = subprocess.run(['git', 'show', f'{BASE}:{path}'], cwd=ROOT, capture_output=True)
        manifest['files'].append({
            'path': path, 'r4_sha256': sha(previous[path]) if path in previous else None,
            'r5_sha256': sha(current[path]) if path in current else None,
            'official_sha256': sha(official.stdout) if official.returncode == 0 else None,
            'local_change_against_official': path in changed,
            'changed_since_r4': previous.get(path) != current.get(path),
        })
    (history / 'source-deltas.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    shutil.copy2(ROOT / 'local/CODE_CHANGES.md', history / 'CODE_CHANGES.md')
    print('Saved code history: official/r4 source bases, full/incremental patches, per-file patches and source hashes.', flush=True)
    return manifest
