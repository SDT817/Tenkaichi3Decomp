"""Preserve real CN3 patches, complete endpoints, resources and offline evidence."""
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import zipfile

from verify_cn3_build import CN2, CN3, HISTORY, OUT as VERIFICATION, ROOT, RUN, SKIP

OUT = ROOT / 'cn3-records'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', 'utf-8')


def source_files(folder):
    files = {}
    for current, dirs, names in os.walk(folder):
        dirs[:] = sorted(d for d in dirs if d not in SKIP)
        for name in sorted(names):
            file = Path(current) / name
            files[file.relative_to(folder).as_posix()] = file.read_bytes()
    return files


def normalized(data):
    if b'\0' in data:
        return data
    try:
        data.decode('utf-8')
    except UnicodeDecodeError:
        return data
    return data.replace(b'\r\n', b'\n')


def save_source_zip(filename, files):
    with zipfile.ZipFile(OUT / filename, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for name, data in sorted(files.items()):
            archive.writestr('Tenkaichi3Decomp-source/' + name, data)


def save_directory_zip(filename, folder):
    with zipfile.ZipFile(OUT / filename, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for current, dirs, names in os.walk(folder):
            dirs[:] = sorted(d for d in dirs if d != '__pycache__')
            for name in sorted(names):
                file = Path(current) / name
                archive.write(file, file.relative_to(folder).as_posix())


def save_patch(filename, before, after):
    """Generate full-index binary-capable patch, then actually reconstruct it."""
    before = {n: normalized(b) for n, b in before.items()}
    after = {n: normalized(b) for n, b in after.items()}

    def put(folder, files):
        folder.mkdir(parents=True)
        for name, data in files.items():
            target = folder / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)

    with tempfile.TemporaryDirectory(prefix='bt3-cn3-code-record-') as temp:
        directory = Path(temp)
        put(directory / 'a', before)
        put(directory / 'b', after)
        result = subprocess.run(['git', '-c', 'core.autocrlf=false', '-c', 'core.safecrlf=false',
                                 'diff', '--no-index', '--no-ext-diff', '--full-index', '--binary',
                                 '--src-prefix=', '--dst-prefix=', '--', 'a', 'b'],
                                cwd=directory, capture_output=True)
        assert result.returncode in (0, 1), result.stderr.decode(errors='replace')
        patch = OUT / filename
        patch.write_bytes(result.stdout)
        restored = directory / 'reconstructed'
        put(restored, before)
        for arguments in (['--check'], ['--whitespace=nowarn']):
            subprocess.run(['git', '-c', 'core.autocrlf=false', 'apply', *arguments, str(patch)],
                           cwd=restored, capture_output=True, check=True)
        actual = source_files(restored)
        assert actual == after, 'Applied patch does not reconstruct the complete target'
    return {'patch': filename, 'patch_sha256': sha(patch.read_bytes()), 'base_files': len(before),
            'target_files': len(after), 'applied_and_all_files_compared': True,
            'normalization': 'UTF-8 source CRLF normalized to LF; ZIP snapshots retain exact raw bytes'}


def main():
    OUT.mkdir(exist_ok=True)
    assert not (OUT / 'build-manifest.json').exists(), 'Keep a completed record immutable; choose a new output for a later edition'
    subprocess.run([os.sys.executable, '-X', 'utf8', 'tools/verify_cn3_build.py'], cwd=ROOT, check=True)
    before, after = source_files(CN2), source_files(CN3)
    captured = json.loads((OUT / 'base-CN2-fixed-source-hashes.json').read_text('utf-8'))
    assert captured == {n: sha(b) for n, b in before.items()}
    official_zip = HISTORY / 'official-0.1.38.1-source.zip'
    with zipfile.ZipFile(official_zip) as archive:
        official = {n.split('/', 1)[1]: archive.read(n) for n in archive.namelist() if not n.endswith('/')}
    shutil.copy2(official_zip, OUT / official_zip.name)
    save_source_zip('base-CN2-fixed-source.zip', before)
    save_source_zip('r5-CN3-complete-local-source.zip', after)
    patches = [save_patch('CN2-fixed-to-CN3.patch', before, after),
               save_patch('from-official-0.1.38.1-to-CN3.patch', official, after)]
    write_json(OUT / 'CN3-source-hashes.json', {n: sha(b) for n, b in after.items()})

    tools = {p.relative_to(ROOT).as_posix(): p.read_bytes() for p in sorted((ROOT / 'tools').iterdir())
             if p.is_file() and p.suffix in ('.py', '.ps1', '.c', '.cpp', '.h')}
    patches.append(save_patch('analysis-tools-CN3.patch', {}, tools))
    for name, data in tools.items():
        path = OUT / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    write_json(OUT / 'analysis-tool-hashes.json', {n: sha(b) for n, b in tools.items()})

    shutil.copytree(ROOT / 'cn3-glyph-mapping', OUT / 'font-mapping-evidence')
    vendor = OUT / 'font-source'
    vendor.mkdir()
    for name in ('ChillRoundGothic_Bold.ttf', 'ChillRoundGothic-OFL.txt'):
        shutil.copy2(ROOT / 'cn3-font-options/vendor' / name, vendor / name)
    references = [
        'terminology-review/menu-transcriptions.json',
        'terminology-review/staged/game-text/translations/ui/zh-CN.json',
        'terminology-review/staged/game-text/translations/labels/zh-CN.json',
        'cn3-body-font-options/records/sample-glyph-identities.json',
    ]
    for name in references:
        target = OUT / 'translation-inputs' / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / name, target)
    save_directory_zip('CN3-local-resources.zip', ROOT / 'cn3-resources')
    save_directory_zip('CN3-offline-verification.zip', VERIFICATION)
    for name in ('resource-checks.json', 'build-checks.json', 'deployment.json'):
        shutil.copy2(VERIFICATION / name, OUT / name)
    for name in ('native-menu-preview.png', 'native-body-preview.png'):
        shutil.copy2(VERIFICATION / name, OUT / name)
    for name in ('persistence-tests.json', 'control-regressions.json', 'settings-fix-code-and-records.zip'):
        shutil.copy2(ROOT / 'settings-save-fix-20261022' / name, OUT / name)
    shutil.copy2(CN3 / 'local/CODE_CHANGES.md', OUT / 'CODE_CHANGES.md')
    shutil.copy2(ROOT / 'CN3-README.md', OUT / 'README.md')
    shutil.copy2(ROOT / 'CN3-README.md', RUN / 'CN3-README.md')

    resources = {p.relative_to(ROOT / 'cn3-resources').as_posix(): sha(p.read_bytes())
                 for p in sorted((ROOT / 'cn3-resources').rglob('*')) if p.is_file()}
    write_json(OUT / 'resource-hashes.json', resources)
    manifest = {'edition': 'r5-CN3', 'official_version': '0.1.38.1',
                'official_base': '11059a6d3e814cf36e6ca1f6307839f61c56f1cc',
                'base': 'CN2 with completed settings persistence repair',
                'git_commits_created': False, 'remote_updates': False,
                'game_launched': False, 'in_game_visual_validation': 'pending user test',
                'runtime_multiplayer_test': 'not performed for CN3',
                'source_files': len(after), 'patches': patches,
                'network_protocol': 5, 'network_objects_unchanged': 5,
                'incremental_changed_objects': ['gs_gs_draw.o', 'gs_menu_text.o'],
                'incremental_unchanged_objects': 355,
                'asset_layout': 'Local preview; four junctions share original disc resources; not standalone',
                'font_source_sha256': sha((vendor / 'ChillRoundGothic_Bold.ttf').read_bytes()),
                'program_files': json.loads((VERIFICATION / 'deployment.json').read_text('utf-8'))['program_files'],
                'historical_evidence_note': 'Final PUA mapping is resources/font-identities.json; early OCR accepted/pending maps are historical, not runtime authority'}
    write_json(OUT / 'build-manifest.json', manifest)
    for path in sorted(OUT.glob('*.zip')):
        with zipfile.ZipFile(path) as archive:
            assert archive.testzip() is None, str(path)
    write_json(OUT / 'record-file-hashes.json', {p.relative_to(OUT).as_posix(): sha(p.read_bytes())
               for p in sorted(OUT.rglob('*')) if p.is_file() and p.name != 'record-file-hashes.json'})
    bundle = ROOT / 'CN3-code-resources-and-records.zip'
    assert not bundle.exists(), 'Keep older exported records intact'
    with zipfile.ZipFile(bundle, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path in sorted(OUT.rglob('*')):
            if path.is_file():
                archive.write(path, 'cn3-records/' + path.relative_to(OUT).as_posix())
    with zipfile.ZipFile(bundle) as archive:
        assert archive.testzip() is None
    write_json(ROOT / 'CN3-records-archive.json', {'file': bundle.name, 'size': bundle.stat().st_size,
               'sha256': sha(bundle.read_bytes()), 'ZIP_integrity': 'passed'})
    print('Saved and reconstructed:', ', '.join(p['patch'] for p in patches), flush=True)
    print('Full source, resources, font mapping and verification records:', OUT, flush=True)
    print('Integrity-checked archive:', bundle, flush=True)


if __name__ == '__main__':
    main()
