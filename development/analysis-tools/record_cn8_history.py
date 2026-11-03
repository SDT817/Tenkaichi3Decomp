"""Preserve exact source endpoints, replayable patches and the matched local build.

No Git repository is changed and no game is launched. Personal game data and
settings are included only in the independent playable copy, never these ZIPs.
"""
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import time
import zipfile

from prepare_cn8_source import ROOT, OUT, OLD, NEW, OFFICIAL_ZIP, normalize
from prepare_cn7_source import source_files

RECORDS = OUT / 'records'
GAME = OUT / 'Test-CN8-Official1391-MenuCache/Tenkaichi3Decomp'
MENU = {'port/src/gs/menu_text.c', 'port/src/gs/menu_text.h', 'src/battle/col_c.c'}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', 'utf-8')


def load_zip(path, strip_root=False):
    with zipfile.ZipFile(path) as z:
        assert z.testzip() is None, path
        return {(n.split('/', 1)[1] if strip_root else n): z.read(n)
                for n in z.namelist() if not n.endswith('/')}


def archive(path, data):
    if path.exists():
        assert load_zip(path) == data, 'Do not overwrite a completed endpoint: ' + str(path)
        return
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for n, b in sorted(data.items()):
            z.writestr(n, b)
    assert load_zip(path) == data, path


def hashes(data):
    return {n: sha(b) for n, b in sorted(data.items())}


def disk_files(folder):
    return {p.relative_to(folder).as_posix(): p.read_bytes()
            for p in sorted(folder.rglob('*')) if p.is_file()}


def changed(before, after):
    return [n for n in sorted(before.keys() | after.keys()) if before.get(n) != after.get(n)]


def save_patch(name, before, after):
    # This is the established CN7 history algorithm. Do not normalize line
    # endings: GitHub's original raw ZIP is a replayable endpoint as well.
    start = time.monotonic()
    with tempfile.TemporaryDirectory(prefix='bt3-cn8-history-') as temporary:
        directory = Path(temporary)
        for folder, endpoint in (('a', before), ('b', after), ('restored', before)):
            target = directory / folder
            target.mkdir()
            for relative, data in endpoint.items():
                path = target / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
        run = subprocess.run(['git', '-c', 'core.autocrlf=false', '-c', 'core.safecrlf=false',
            'diff', '--no-index', '--no-renames', '--no-ext-diff', '--full-index', '--binary',
            '--src-prefix=', '--dst-prefix=', '--', 'a', 'b'], cwd=directory, capture_output=True)
        assert run.returncode in (0, 1), run.stderr.decode(errors='replace')
        patch = RECORDS / name
        if patch.exists():
            assert patch.read_bytes() == run.stdout, patch
        else:
            patch.write_bytes(run.stdout)
        for flags in (['--check'], ['--whitespace=nowarn']):
            result = subprocess.run(['git', '-c', 'core.autocrlf=false', 'apply', *flags, str(patch)],
                cwd=directory / 'restored', capture_output=True)
            assert result.returncode == 0, result.stderr.decode(errors='replace')
        assert disk_files(directory / 'restored') == after
    print('Replayed', name, 'in', round(time.monotonic() - start, 1), 's', flush=True)
    return {'patch': name, 'sha256': sha(patch.read_bytes()), 'bytes': patch.stat().st_size,
            'changed_files': changed(before, after), 'base_files': len(before),
            'target_files': len(after), 'check_and_apply_passed': True,
            'complete_target_bytes_compared': True, 'line_ending_normalization': False}


def source_endpoint(path):
    return {n: b for n, b in source_files(path).items()
            if not n.startswith(('records/', 'build_release/'))}


def main():
    RECORDS.mkdir(exist_ok=True)
    official = load_zip(OFFICIAL_ZIP, strip_root=True)
    old = source_endpoint(OLD)
    merged = load_zip(RECORDS / 'merged-before-menu-optimization-source.zip')
    final = source_endpoint(NEW)
    initial = json.loads((RECORDS / 'initial-merge.json').read_text('utf-8'))
    assert hashes({n: normalize(b) for n, b in old.items()}) == initial['previous_sha256']
    assert hashes({n: normalize(b) for n, b in official.items()}) == initial['official_sha256']
    assert set(changed(merged, final)) == MENU | {
        'port/src/gs/ui.cpp', 'local/CN8_MENU_CACHE_CHANGES.md', 'local/build_cn8.py'}
    # Separate the independently mergeable runtime changes from build records.
    menu = dict(merged)
    for n in MENU:
        menu[n] = final[n]
    update = dict(menu)
    update['port/src/gs/ui.cpp'] = final['port/src/gs/ui.cpp']
    shutil.copy2(OFFICIAL_ZIP, RECORDS / 'official-v0.1.39.1-source.zip')
    ancestor = OLD / 'records/official-0.1.38.9-source.zip'
    assert ancestor.is_file()
    shutil.copy2(ancestor, RECORDS / ancestor.name)
    for name, endpoint in [('previous-r11-nonlobby-source.zip', old),
                           ('final-r14-CN8-source.zip', final)]:
        archive(RECORDS / name, endpoint)
        print('Verified source archive', name, len(endpoint), 'files', flush=True)
    patches = [save_patch(name, a, b) for name, a, b in [
        ('01-official1391-to-retained-CN7-Wii-I.patch', official, merged),
        ('02-main-menu-prewarm-only.patch', merged, menu),
        ('03-disable-local-auto-update-only.patch', menu, update),
        ('04-local-build-and-documentation.patch', update, final),
        ('official1391-to-final-CN8-complete.patch', official, final),
        ('previous-r11-to-final-CN8-complete.patch', old, final)]]
    assert set(patches[1]['changed_files']) == MENU
    assert patches[2]['changed_files'] == ['port/src/gs/ui.cpp']
    for n, endpoint in [('official1391-raw', official), ('previous-r11-raw', old),
                        ('merged-before-optimization', merged), ('final-r14-raw', final)]:
        write(RECORDS / (n + '-source-sha256.json'), hashes(endpoint))
    build = {}
    # Preserve generated shaders/headers and blank skeleton data objects used
    # by this build. They contain no user's ISO data and no original game disc.
    for folder in ('gen', 'obj_data_win64'):
        for p in (NEW / 'port/build' / folder).rglob('*'):
            if p.is_file():
                build[p.relative_to(NEW).as_posix()] = p.read_bytes()
    build['BUILD-PREREQUISITES.txt'] = (
        'Unzip final-r14-CN8-source.zip, then this archive into the same root.\n'
        'These are the generated headers/shaders and SKELETON blank data objects actually used.\n'
        'The source objects are rebuilt by local/build_cn8.py. No game disc data is included.\n'
        'Toolchain: E:\\BT3-Wii-tools\\mingw64 and E:\\BT3-Wii-tools\\ucrt64.\n'
        'Python: E:\\Phyton\\python.exe -X utf8 local/build_cn8.py\n'
        'The existing Python libclang package (clang.cindex) must also be installed.\n'
        'Generated source paths and local adapters are preserved exactly, not relocated.\n'
        'Rebuilding elsewhere can require changing BT3_LOCAL_TOOLS and Python/toolchain paths.\n'
        'The timestamp/debug metadata in a rebuilt EXE may differ.\n'
    ).encode('utf-8')
    archive(RECORDS / 'actual-build-prerequisites.zip', build)
    write(RECORDS / 'actual-build-prerequisites-sha256.json', hashes(build))
    assert (OUT / 'verification/deployment.json').is_file(), 'Wait for playable copy to finish'
    deploy = json.loads((OUT / 'verification/deployment.json').read_text('utf-8'))
    binaries = {}
    for n, h in deploy['programs'].items():
        b = (GAME / n).read_bytes()
        assert sha(b) == h
        binaries[n] = b
    for p in (NEW / 'port/build/cn8-logs').glob('*'):
        if p.is_file():
            binaries['build-logs/' + p.name] = p.read_bytes()
    for n in ('bt3.exe.map', 'stubs.txt', 'link.rsp'):
        p = NEW / 'port/build' / n
        assert p.is_file(), p
        binaries['build-logs/' + n] = p.read_bytes()
    binaries['CN8-Build.json'] = (GAME / 'CN8-Build.json').read_bytes()
    archive(RECORDS / 'matched-binaries-and-build-logs.zip', binaries)
    write(RECORDS / 'matched-binaries-sha256.json', hashes(binaries))
    # All local mod assets, including all eleven plane warmup files. No disc,
    # saves, settings, controller profile, song or log is redistributed.
    assets = {}
    for folder in ('fonts', 'gamedata/game-text', 'gamedata/mods'):
        for p in (GAME / folder).rglob('*'):
            if p.is_file():
                assets[p.relative_to(GAME).as_posix()] = p.read_bytes()
    assert len([n for n in assets if n.startswith('gamedata/game-text/font-warmup/')]) == 11
    archive(RECORDS / 'CN8-complete-Chinese-resources.zip', assets)
    write(RECORDS / 'CN8-complete-Chinese-resources-sha256.json', hashes(assets))
    update_files = dict(assets)
    for folder in ('tbo', 'translations', 'licenses'):
        for p in (GAME / folder).rglob('*'):
            if p.is_file():
                update_files[p.relative_to(GAME).as_posix()] = p.read_bytes()
    for n in (*deploy['programs'], '01-Play-Immediate.cmd', '02-Capture-menu.cmd',
              'CN8-source-changes.md', '使用说明.txt'):
        update_files[n] = (GAME / n).read_bytes()
    update_files['CN8-version.json'] = json.dumps({
        'official_version': deploy['official_version'], 'official_commit': deploy['official_commit'],
        'edition': deploy['edition'], 'protocol': 6, 'private_lobby_included': False,
        'automatic_update_disabled': True, 'programs': deploy['programs'],
    }, ensure_ascii=False, indent=2).encode('utf-8') + b'\n'
    update_files['安装说明.txt'] = (
        'CN8 本地更新包，基于官方 v0.1.39.1。\n'
        '请先保留原目录副本，再解压覆盖已安装该版本的游戏目录。\n'
        '本包已在工作区准备完成，没有自动覆盖现有安装。\n'
        '包括配套 EXE/mem/DAT、SDL3、汉化字体/文本/资源和官方 UI 图片。\n'
        '不包括游戏原始数据、个人设置、存档、Wii 预设或自建大厅。\n'
        '独立测试目录已经准备好，不必先安装这个更新包即可测试。\n'
        '先手动验证标题“继续游戏”进入主菜单的表现；仍卡时使用诊断脚本。\n'
        '自动更新已关闭。官方协议6，联机双方需同一新版。\n'
    ).encode('utf-8-sig')
    archive(OUT / 'CN8-Official1391-Chinese-Wii-MenuCache-update.zip', update_files)
    write(RECORDS / 'update-package-files-sha256.json', hashes(update_files))
    evidence = {}
    for p in (OUT / 'verification').rglob('*'):
        if p.is_file():
            evidence[p.relative_to(OUT).as_posix()] = p.read_bytes()
    for name in ('prepare_cn8_source.py', 'resolve_cn8_merge.py', 'bench_cn8_mainmenu.py',
                 'verify_cn8_native.py', 'verify_cn8_boundaries.py', 'package_cn8_test.py',
                 'record_cn8_history.py', 'prepare_cn7_source.py'):
        evidence['tools/' + name] = (ROOT / 'tools' / name).read_bytes()
    archive(RECORDS / 'offline-verification-and-tools.zip', evidence)
    report = {'official_version': '0.1.39.1', 'official_commit': deploy['official_commit'],
        'official_raw_zip_sha256': sha(OFFICIAL_ZIP.read_bytes()), 'previous_branch': OLD.name,
        'final_source': str(NEW), 'playable_copy': str(GAME),
        'private_lobby_included': False, 'git_commit_push_or_PR': False,
        'previous_source_endpoint_unchanged': True, 'patches': patches,
        'all_archives_raw_bytes_verified': True, 'game_launched': False,
        'live_FPS_and_transition_test': 'pending user',
        'records_exclude_original_disc_and_personal_settings': True,
        'update_excludes_original_disc_and_personal_settings': True,
        'runtime_delta_from_retained_merge': sorted(MENU | {'port/src/gs/ui.cpp'}),
        'programs': deploy['programs']}
    write(RECORDS / 'replay-verification.json', report)
    print('All source patches replayed and archive contents verified.', flush=True)
    print('Playable copy:', GAME, flush=True)


if __name__ == '__main__':
    main()
