"""Compile the two CN7 display objects against the accepted I object set."""
import contextlib
import hashlib
import io
import json
import build_windows as build


def hashes(folder):
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.glob('*.o')}


if __name__ == '__main__':
    before = hashes(build.undefined.OBJ)
    data = hashes(build.ROOT / 'port/build/obj_data_win64')
    obj, source, error, pending = build.cc(build.ROOT / 'src/battle/btl_script.c')
    assert obj is not None and not pending, error
    log = 'btl_script.c\n' + error
    print('Compiled btl_script.c', flush=True)
    result = build.undefined.run(['gcc', '-m32', '-std=gnu99', '-c', '-O2', '-g', '-fno-pic',
        '-msse2', '-mfpmath=sse', '-fno-strict-aliasing', '-Wall', '-Wno-unused',
        '-Wno-misleading-indentation', '-Iport/build/gen/gs',
        str(build.ROOT / 'port/src/gs/ui_text_translate.c'),
        '-o', str(build.undefined.OBJ / 'gs_ui_text_translate.o')],
        cwd=build.ROOT, capture_output=True, text=True)
    log += 'ui_text_translate.c\n' + result.stdout + result.stderr
    (build.ROOT / 'port/build/cn7-immediate-i-compile.log').write_text(log, 'utf-8')
    result.check_returncode()
    after = hashes(build.undefined.OBJ)
    changed = sorted(n for n in before if before[n] != after[n])
    assert changed == ['battle_btl_script.o', 'gs_ui_text_translate.o'], changed
    assert before.keys() == after.keys()
    assert data == hashes(build.ROOT / 'port/build/obj_data_win64')
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        import link
    log = stream.getvalue()
    (build.ROOT / 'port/build/cn7-immediate-i-link.log').write_text(log, 'utf-8')
    assert 'link OK' in log and '103 stubs;' in log, log
    (build.ROOT / 'port/build/cn7-immediate-i-object-checks.json').write_text(json.dumps({
        'changed_objects': changed, 'before': before, 'after': after, 'data_objects': data,
    }, indent=2) + '\n', 'utf-8')
    print(log, flush=True)
