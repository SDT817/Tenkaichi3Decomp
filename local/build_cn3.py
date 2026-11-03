"""Compile only the menu-font and shared-atlas display changes, then relink."""
import build_windows as build

if __name__ == '__main__':
    for name in ('gs_draw.c', 'menu_text.c'):
        source = build.ROOT / 'port/src/gs' / name
        obj = build.undefined.OBJ / ('gs_' + source.stem + '.o')
        run = build.undefined.run(['gcc', '-m32', '-std=gnu99', '-c', '-O2', '-g', '-fno-pic',
                               '-msse2', '-mfpmath=sse', '-fno-strict-aliasing', '-Wall', '-Wno-unused',
                               '-Wno-misleading-indentation', '-Iport/build/gen/gs', str(source), '-o', str(obj)],
                              cwd=build.ROOT, capture_output=True, text=True)
        if run.returncode:
            raise RuntimeError(run.stderr)
        print('Compiled menu renderer:', obj.name, flush=True)
    import link
