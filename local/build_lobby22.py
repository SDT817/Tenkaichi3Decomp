"""Keep Test4 battle objects; rebuild only presentation, update and version UI."""
import contextlib
import hashlib
import io
import json
import build_windows as b

base = b.ROOT.parent/'Tenkaichi3Decomp-WiiLocal-r21-TrunksFlight'
def hashes(path):
    return {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in path.glob('*.o')}

before = hashes(base/'port/build/obj_win64')
logs = []
sources = [('ui.cpp','cxx_ui'),('gs_gpu.c','gs_gs_gpu'),('net_update.c','gs_net_update'),
           ('online_lobby.cpp','cxx_online_lobby')] # header-only edition number used by the lobby
for name,obj in sources:
    cpp = name.endswith('.cpp')
    cmd = ['g++' if cpp else 'gcc','-m32','-std=c++17' if cpp else '-std=gnu99',
           '-c','-O2','-g','-fno-pic','-msse2','-mfpmath=sse']
    cmd += ['-fno-exceptions','-fno-rtti','-w'] if cpp else ['-fno-strict-aliasing','-Wall','-Wno-unused','-Wno-misleading-indentation']
    cmd += ['-Iport/third_party/imgui','-Iport/src/gs','-Iport/src','-Iport/build/gen/gs',
            str(b.ROOT/'port/src/gs'/name),'-o',str(b.undefined.OBJ/(obj+'.o'))]
    r = b.undefined.run(cmd,cwd=b.ROOT,capture_output=True,text=True)
    logs.append(name+'\n'+r.stdout+r.stderr)
    (b.ROOT/'port/build/lobby22-compile.log').write_text('\n'.join(logs),'utf-8')
    assert r.returncode == 0, r.stderr
    print('Compiled',name,flush=True)
after = hashes(b.undefined.OBJ)
changed = sorted(n for n in before if before[n] != after[n])
assert changed == sorted(obj+'.o' for _,obj in sources),changed
assert hashes(base/'port/build/obj_data_win64') == hashes(b.ROOT/'port/build/obj_data_win64')
output = io.StringIO()
with contextlib.redirect_stdout(output):
    import link
log = output.getvalue()
(b.ROOT/'port/build/lobby22-link.log').write_text(log,'utf-8')
assert '103 stubs; link OK' in log,log
(b.ROOT/'port/build/lobby22-objects.json').write_text(json.dumps({
    'changed_objects':changed,'before':before,'after':after},indent=2)+'\n','utf-8')
print(log,flush=True)
