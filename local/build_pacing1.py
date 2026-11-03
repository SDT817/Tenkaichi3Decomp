"""Build renderer diagnostics, preserving every game/network/data object."""
import contextlib
import hashlib
import io
import json
import build_windows as build


def hashes(folder):
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.glob('*.o')}


if __name__ == '__main__':
    before = hashes(build.undefined.OBJ)
    data_before = hashes(build.ROOT / 'port/build/obj_data_win64')
    log = ''
    for name in ['gs_core', 'gs_draw', 'gs_gpu', 'perf_trace']:
        source = build.ROOT / 'port/src/gs' / (name + '.c')
        obj = build.undefined.OBJ / ('gs_' + name + '.o')
        result = build.undefined.run(['gcc', '-m32', '-std=gnu99', '-c', '-O2', '-g', '-fno-pic',
            '-msse2', '-mfpmath=sse', '-fno-strict-aliasing', '-Wall', '-Wno-unused',
            '-Wno-misleading-indentation', '-Iport/build/gen/gs', str(source), '-o', str(obj)],
            cwd=build.ROOT, capture_output=True, text=True)
        log += name + '\n' + result.stdout + result.stderr
        (build.ROOT / 'port/build/pacing1-compile.log').write_text(log, 'utf-8')
        result.check_returncode()
        print('Compiled', name, flush=True)
    after = hashes(build.undefined.OBJ)
    changed = sorted(n for n in before if before[n] != after[n])
    added = sorted(after.keys() - before.keys())
    assert changed == ['gs_gs_core.o', 'gs_gs_draw.o', 'gs_gs_gpu.o'], changed
    assert added == ['gs_perf_trace.o'], added
    assert data_before == hashes(build.ROOT / 'port/build/obj_data_win64')
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        import link
    log = output.getvalue()
    (build.ROOT / 'port/build/pacing1-link.log').write_text(log, 'utf-8')
    assert 'link OK' in log and '103 stubs;' in log, log
    (build.ROOT / 'port/build/pacing1-object-checks.json').write_text(json.dumps({
        'changed_objects': changed, 'added_objects': added, 'before': before,
        'after': after, 'data_objects': data_before,
    }, indent=2) + '\n', 'utf-8')
    print(log, flush=True)
