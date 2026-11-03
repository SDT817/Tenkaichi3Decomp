"""Rebuild only the settings store, then relink with the existing CN2 objects."""
import build_windows as build


if __name__ == '__main__':
    source = build.ROOT / 'port/src/plat_settings.c'
    obj = build.undefined.OBJ / 'pc_plat_settings.o'
    cmd = ['gcc', '-m32', '-std=gnu99', '-c', '-O2', '-g', '-fno-pic', '-malign-double',
           '-fno-strict-aliasing', '-ffp-contract=off', '-fno-builtin', '-w', '-Iinclude',
           '-Iport/include', '-Iport/src', '-msoft-float', '-mno-sse', '-mno-mmx',
           '-DSF_FAST_CALLS', '-include', 'math.h', '-include', 'stdlib.h', '-include', 'port_libm.h']
    result = build.undefined.compile_ee(cmd, source, obj)
    if result.returncode or getattr(result, 'pending', None):
        raise RuntimeError(result.stderr)
    print('Compiled settings store:', obj.name, flush=True)
    import link
