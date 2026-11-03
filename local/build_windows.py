"""Local Windows build adapter. The official tracked build scripts stay unchanged."""
from pathlib import Path
import os
import sys
from native_paths import install
install()

ROOT = Path(__file__).resolve().parents[1]
TOOLS = Path(os.environ.get('BT3_LOCAL_TOOLS', r'E:\BT3-Wii-tools'))
os.chdir(ROOT)
os.environ.update(BT3_CC='win64', BT3_SKELETON='1', BT3_SDL3=str(TOOLS / 'ucrt64'))
os.environ['PATH'] = str(TOOLS / 'mingw64/bin') + ';' + str(TOOLS / 'ucrt64/bin') + ';' + os.environ['PATH']
sys.path.insert(0, str(ROOT / 'port/tools'))
import clang.cindex as ci
ci.Config.set_library_file(str(TOOLS / 'ucrt64/bin/libclang.dll'))
import portsrc
import ptr32
import undefined
ci.CursorKind.from_id = staticmethod(ptr32._known_kind)

def sources():
    fs = [ROOT / 'src/main.c'] + sorted((ROOT / 'src/sys').glob('*.c')) + sorted((ROOT / 'src/battle').glob('*.c')) + sorted((ROOT / 'src/menu').glob('*.c'))
    return [f for f in fs if f.relative_to(ROOT).as_posix() not in portsrc.REPLACED]

def cc(f):
    o = undefined.OBJ / (f.relative_to(ROOT / 'src').as_posix().replace('/', '_')[:-2] + '.o')
    src, done, missing = portsrc.prepare(f)
    r = undefined.compile_ee(undefined.CC + [f'-I{f.parent}'], src, o)
    if missing: print('no C for:', f.name, ' '.join(missing))
    return o if r.returncode == 0 else None, f, r.stderr, getattr(r, 'pending', None)

original_transform = ptr32.transform
original_compile_ee = undefined.compile_ee

def compile_ee(cmd, src, obj):
    # Relative source/include paths avoid octal-escaped Chinese checkout names
    # in clang's preprocessor markers. No compiler or runtime flags change.
    prefix = str(ROOT).replace('\\', '/') + '/'
    def relative(value):
        value = str(value).replace('\\', '/')
        if value.startswith('-I' + prefix):
            return '-I' + value[len(prefix) + 2:]
        return value[len(prefix):] if value.startswith(prefix) else value
    return original_compile_ee([relative(a) for a in cmd], relative(src), obj)
def transform(filename, args):
    return original_transform(filename, args + ['-Wno-error=return-type'])
portsrc.sources = sources
undefined.cc = cc
undefined.compile_ee = compile_ee
ptr32.transform = transform

if __name__ == '__main__':
    if sys.argv[1:] == ['link']:
        import link
    elif sys.argv[1:2] == ['cpp']:
        for name in sys.argv[2:]:
            f = ROOT / 'port/src/gs' / name
            o = undefined.OBJ / ('cxx_' + f.stem + '.o')
            r = undefined.run(['g++', '-m32', '-std=c++17', '-c', '-O2', '-g', '-fno-pic', '-msse2', '-mfpmath=sse',
                               '-fno-exceptions', '-fno-rtti', '-w', '-Iport/third_party/imgui', '-Iport/src/gs',
                               '-Iport/build/gen/gs', str(f), '-o', str(o)], cwd=ROOT, capture_output=True, text=True)
            if r.returncode: raise RuntimeError(r.stderr)
            print('Compiled', name, flush=True)
    else:
        undefined.main()
