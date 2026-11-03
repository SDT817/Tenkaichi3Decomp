"""Incremental CN2 build; compile only Chinese display and text changes.
All objects are copied into this isolated checkout before building.
"""
import build_windows as build

if __name__ == '__main__':
    for name in ('col_c.c', 'btl_seq.c'):
        obj, source, error, pending = build.cc(build.ROOT / 'src/battle' / name)
        if obj is None or pending:
            raise RuntimeError(error)
        print('Compiled text display:', obj.name, flush=True)
    for name in ('menu_labels.c', 'menu_text.c', 'ui_text_translate.c'):
        f = build.ROOT / 'port/src/gs' / name
        o = build.undefined.OBJ / ('gs_' + f.stem + '.o')
        r = build.undefined.run(['gcc', '-m32', '-std=gnu99', '-c', '-O2', '-g', '-fno-pic',
                                 '-msse2', '-mfpmath=sse', '-fno-strict-aliasing', '-Wall', '-Wno-unused',
                                 '-Wno-misleading-indentation', '-Iport/build/gen/gs', str(f), '-o', str(o)],
                                cwd=build.ROOT, capture_output=True, text=True)
        if r.returncode:
            raise RuntimeError(r.stderr)
        print('Compiled menu display:', o.name, flush=True)
    import link
