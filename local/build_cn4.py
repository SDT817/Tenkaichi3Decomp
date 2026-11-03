"""Compile only the shared CJK atlas placement fix, then relink."""
import build_windows as build

if __name__ == '__main__':
    source = build.ROOT / 'port/src/gs/menu_text.c'
    obj = build.undefined.OBJ / 'gs_menu_text.o'
    run = build.undefined.run(['gcc', '-m32', '-std=gnu99', '-c', '-O2', '-g', '-fno-pic',
                               '-msse2', '-mfpmath=sse', '-fno-strict-aliasing', '-Wall', '-Wno-unused',
                               '-Wno-misleading-indentation', '-Iport/build/gen/gs', str(source), '-o', str(obj)],
                              cwd=build.ROOT, capture_output=True, text=True)
    if run.returncode:
        raise RuntimeError(run.stderr)
    print('Compiled shared CJK renderer:', obj.name, flush=True)
    import link
