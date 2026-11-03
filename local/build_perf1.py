"""Recompile the changed matcher with the same Windows build flags; keep every other object."""
import hashlib, io, contextlib, json
import build_windows as build

def hashes():
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in build.undefined.OBJ.glob('*.o')}

if __name__ == '__main__':
    before = hashes()
    f = build.ROOT/'port/src/gs/menu_labels.c'
    result = build.undefined.run(['gcc', '-m32', '-std=gnu99', '-c', '-O2', '-g', '-fno-pic',
        '-msse2', '-mfpmath=sse', '-fno-strict-aliasing', '-Wall', '-Wno-unused',
        '-Wno-misleading-indentation', '-Iport/build/gen/gs', str(f),
        '-o', str(build.undefined.OBJ/'gs_menu_labels.o')], cwd=build.ROOT, capture_output=True, text=True)
    result.check_returncode()
    after = hashes()
    changed = sorted(k for k in before if before[k] != after[k])
    assert changed == ['gs_menu_labels.o'], changed
    log = io.StringIO()
    with contextlib.redirect_stdout(log):
        import link
    output = log.getvalue()
    (build.ROOT/'port/build/perf1-link.log').write_text(output, 'utf-8')
    assert 'link OK' in output and '103 stubs;' in output
    (build.ROOT/'port/build/perf1-object-checks.json').write_text(json.dumps({
        'changed_objects': changed, 'before': before, 'after': after}, indent=2)+'\n', 'utf-8')
    print(output, flush=True)
