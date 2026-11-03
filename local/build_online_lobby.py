"""Incremental private lobby build against the exact CN8/0.1.39.1 objects."""
import contextlib
import hashlib
import io
import json
import build_windows as build

def hashes(folder):
    return {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.glob('*.o')}

if __name__ == '__main__':
    base = build.ROOT.parent/'Tenkaichi3Decomp-WiiLocal-r14-CN8-MenuCache'
    before = hashes(base/'port/build/obj_win64')
    log = ''
    for name in ['net.c','net_match.c','ui.cpp','online_ping.cpp','online_lobby.cpp']:
        cpp = name.endswith('.cpp')
        target = build.undefined.OBJ/(('cxx_' if cpp else 'gs_')+name.split('.')[0]+'.o')
        cmd = ['g++' if cpp else 'gcc','-m32','-std=c++17' if cpp else '-std=gnu99',
               '-c','-O2','-g','-fno-pic','-msse2','-mfpmath=sse']
        cmd += ['-fno-exceptions','-fno-rtti','-w'] if cpp else ['-fno-strict-aliasing','-Wall','-Wno-unused','-Wno-misleading-indentation']
        cmd += ['-Iport/third_party/imgui','-Iport/src/gs','-Iport/build/gen/gs',
                str(build.ROOT/'port/src/gs'/name),'-o',str(target)]
        result = build.undefined.run(cmd,cwd=build.ROOT,capture_output=True,text=True)
        log += name+'\n'+result.stdout+result.stderr
        (build.ROOT/'port/build/online-lobby-compile.log').write_text(log,'utf-8')
        if result.returncode:raise RuntimeError(result.stderr)
        print('Compiled',name,flush=True)
    after = hashes(build.undefined.OBJ)
    changed = sorted(n for n in before if before[n] != after[n])
    assert changed == ['cxx_ui.o','gs_net.o','gs_net_match.o'], changed
    assert sorted(after.keys()-before.keys()) == ['cxx_online_lobby.o','cxx_online_ping.o']
    assert hashes(base/'port/build/obj_data_win64') == hashes(build.ROOT/'port/build/obj_data_win64')
    output = io.StringIO()
    with contextlib.redirect_stdout(output):import link
    log = output.getvalue()
    (build.ROOT/'port/build/online-lobby-link.log').write_text(log,'utf-8')
    assert 'link OK' in log,log
    (build.ROOT/'port/build/online-lobby-objects.json').write_text(json.dumps({
        'changed_objects':changed,'new_objects':sorted(after.keys()-before.keys()),
        'before':before,'after':after,'data_objects':hashes(build.ROOT/'port/build/obj_data_win64'),
    },indent=2)+'\n','utf-8')
    print(log,flush=True)
