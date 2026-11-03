"""Rebuild the v0.1.38.7 merge using the existing Windows adapter and official flags."""
import contextlib
import io
import build_windows as build

if __name__ == '__main__':
    output = io.StringIO()
    try:
        with contextlib.redirect_stdout(output):
            build.undefined.main()
    finally:
        log = output.getvalue()
        (build.ROOT/'port/build/cn6-compile.log').write_text(log, 'utf-8')
    print(log, flush=True)
    if 'FAILED' in log:
        raise RuntimeError('Compilation failed; do not link stale objects')
    import link
