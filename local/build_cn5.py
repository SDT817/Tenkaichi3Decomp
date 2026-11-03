"""Rebuild the merged release with the existing official algorithms and flags."""
import contextlib
import io
import build_windows as build


if __name__=='__main__':
    output=io.StringIO()
    with contextlib.redirect_stdout(output):
        build.undefined.main()
    log=output.getvalue()
    (build.ROOT/'port/build/cn5-compile.log').write_text(log,'utf-8')
    print(log,flush=True)
    if 'FAILED' in log:
        raise RuntimeError('Compilation failed; preserve log and do not link stale objects')
    import link
