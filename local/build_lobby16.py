"""Only rebuild UI, lobby focus and the embedded default presentation choice."""
import contextlib
import hashlib
import io
import json
import build_windows as build

def hashes(folder):
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.glob('*.o')}

if __name__ == '__main__':
    base = build.ROOT.parent / 'Tenkaichi3Decomp-WiiLocal-r15-Online1391'
    before = hashes(base / 'port/build/obj_win64')
    log = ''
    for name in ['gs_gpu.c', 'ui.cpp', 'online_lobby.cpp']:
        cpp = name.endswith('.cpp')
        target = build.undefined.OBJ / (('cxx_' if cpp else 'gs_') + name.split('.')[0] + '.o')
        cmd = ['g++' if cpp else 'gcc', '-m32', '-std=c++17' if cpp else '-std=gnu99',
               '-c', '-O2', '-g', '-fno-pic', '-msse2', '-mfpmath=sse']
        cmd += ['-fno-exceptions', '-fno-rtti', '-w'] if cpp else ['-fno-strict-aliasing', '-Wall', '-Wno-unused', '-Wno-misleading-indentation']
        cmd += ['-Iport/third_party/imgui', '-Iport/src/gs', '-Iport/build/gen/gs',
                str(build.ROOT / 'port/src/gs' / name), '-o', str(target)]
        result = build.undefined.run(cmd, cwd=build.ROOT, capture_output=True, text=True)
        log += name + '\n' + result.stdout + result.stderr
        (build.ROOT / 'port/build/lobby16-compile.log').write_text(log, 'utf-8')
        if result.returncode:
            raise RuntimeError(result.stderr)
        print('Compiled', name, flush=True)
    after = hashes(build.undefined.OBJ)
    changed = sorted(n for n in before if before[n] != after[n])
    assert changed == ['cxx_online_lobby.o', 'cxx_ui.o', 'gs_gs_gpu.o'], changed
    assert before.keys() == after.keys()
    assert hashes(base / 'port/build/obj_data_win64') == hashes(build.ROOT / 'port/build/obj_data_win64')
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        import link
    log = output.getvalue()
    (build.ROOT / 'port/build/lobby16-link.log').write_text(log, 'utf-8')
    assert 'link OK' in log, log
    (build.ROOT / 'port/build/lobby16-objects.json').write_text(json.dumps({
        'changed_objects': changed, 'before': before, 'after': after,
        'data_objects': hashes(build.ROOT / 'port/build/obj_data_win64'),
    }, indent=2) + '\n', 'utf-8')
    print(log, flush=True)
