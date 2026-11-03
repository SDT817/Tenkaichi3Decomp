"""Full build on verified official 0.1.39.1 with the existing Windows adapter."""
import contextlib
import io
from pathlib import Path
import build_windows as build

if __name__ == '__main__':
    logs = build.ROOT/'port/build/cn8-logs'
    logs.mkdir(exist_ok=True)
    stream = io.StringIO()
    try:
        with contextlib.redirect_stdout(stream):
            build.undefined.main()
    finally:
        text = stream.getvalue()
        (logs/'compile.log').write_text(text,'utf-8')
    print(text,flush=True)
    assert 'FAILED' not in text, 'Do not link incomplete objects'
    stream = io.StringIO()
    try:
        with contextlib.redirect_stdout(stream):
            import link
    finally:
        text = stream.getvalue()
        (logs/'link.log').write_text(text,'utf-8')
    print(text,flush=True)
    assert 'link OK' in text
    assert len((build.ROOT/'port/build/bt3.exe.mem').read_text().splitlines()) > 2
