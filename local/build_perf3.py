"""Recompile the glyph atlas cache only, keeping every other compiled object unchanged."""
import contextlib
import hashlib
import io
import json
import build_windows as build


def hashes(directory):
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in directory.glob('*.o')}


if __name__ == '__main__':
    before = hashes(build.undefined.OBJ)
    data_before = hashes(build.ROOT / 'port/build/obj_data_win64')
    source = build.ROOT / 'port/src/gs/menu_text.c'
    result = build.undefined.run(['gcc', '-m32', '-std=gnu99', '-c', '-O2', '-g', '-fno-pic',
        '-msse2', '-mfpmath=sse', '-fno-strict-aliasing', '-Wall', '-Wno-unused',
        '-Wno-misleading-indentation', '-Iport/build/gen/gs', str(source),
        '-o', str(build.undefined.OBJ / 'gs_menu_text.o')], cwd=build.ROOT, capture_output=True, text=True)
    (build.ROOT / 'port/build/perf3-compile.log').write_text(result.stdout + result.stderr, 'utf-8')
    result.check_returncode()
    after = hashes(build.undefined.OBJ)
    changed = sorted(name for name in before if before[name] != after[name])
    assert changed == ['gs_menu_text.o'], changed
    assert data_before == hashes(build.ROOT / 'port/build/obj_data_win64')
    log = io.StringIO()
    with contextlib.redirect_stdout(log):
        import link
    output = log.getvalue()
    (build.ROOT / 'port/build/perf3-link.log').write_text(output, 'utf-8')
    assert 'link OK' in output and '103 stubs;' in output
    (build.ROOT / 'port/build/perf3-object-checks.json').write_text(json.dumps({
        'changed_objects': changed, 'before': before, 'after': after, 'data_objects': data_before,
    }, indent=2) + '\n', 'utf-8')
    print(output, flush=True)
