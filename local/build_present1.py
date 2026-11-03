"""Build the present-mode diagnostic with the official flags."""
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
    for name in ['gs_gpu']:
        result = build.undefined.run(['gcc', '-m32', '-std=gnu99', '-c', '-O2', '-g', '-fno-pic',
            '-msse2', '-mfpmath=sse', '-fno-strict-aliasing', '-Wall', '-Wno-unused',
            '-Wno-misleading-indentation', '-Iport/build/gen/gs',
            str(build.ROOT / 'port/src/gs' / (name + '.c')),
            '-o', str(build.undefined.OBJ / ('gs_' + name + '.o'))],
            cwd=build.ROOT, capture_output=True, text=True)
        log += name + '\n' + result.stdout + result.stderr
        (build.ROOT / 'port/build/present1-compile.log').write_text(log, 'utf-8')
        result.check_returncode()
        print('Compiled', name, flush=True)
    after = hashes(build.undefined.OBJ)
    changed = sorted(n for n in before if before[n] != after[n])
    assert changed == ['gs_gs_gpu.o'], changed
    assert before.keys() == after.keys()
    assert data_before == hashes(build.ROOT / 'port/build/obj_data_win64')
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        import link
    log = stream.getvalue()
    (build.ROOT / 'port/build/present1-link.log').write_text(log, 'utf-8')
    assert 'link OK' in log and '103 stubs;' in log, log
    (build.ROOT / 'port/build/present1-object-checks.json').write_text(json.dumps({
        'changed_objects': changed, 'before': before, 'after': after, 'data_objects': data_before,
    }, indent=2) + '\n', 'utf-8')
    print(log, flush=True)
