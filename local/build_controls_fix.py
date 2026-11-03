"""Full build on official 0.1.38.9, using the existing native Windows adapter."""
import contextlib
import io
from pathlib import Path
import shutil
import build_windows as build

if __name__ == '__main__':
    previous = build.ROOT.parent / 'Tenkaichi3Decomp-WiiLocal-r8-CN7-ImmediateI/port/build'
    for name in ('gen', 'obj_data_win64'):
        target = build.ROOT / 'port/build' / name
        if not target.exists():
            shutil.copytree(previous / name, target)
    output = io.StringIO()
    try:
        with contextlib.redirect_stdout(output):
            build.undefined.main()
    finally:
        log = output.getvalue()
        (build.ROOT / 'records/build-compile.log').write_text(log, encoding='utf-8')
    print(log, flush=True)
    assert 'FAILED' not in log, 'Do not link an incomplete build'
    output = io.StringIO()
    try:
        with contextlib.redirect_stdout(output):
            import link
    finally:
        log = output.getvalue()
        (build.ROOT / 'records/build-link.log').write_text(log, encoding='utf-8')
    print(log, flush=True)
    assert 'link OK' in log and len((build.ROOT / 'port/build/bt3.exe.mem').read_text().splitlines()) > 2
