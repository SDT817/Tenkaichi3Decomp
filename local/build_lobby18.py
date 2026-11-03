"""Only rebuild the two UI objects, updater version, and two pause hooks."""
import contextlib
import io
import json
import hashlib
import build_windows as b
base=b.ROOT.parent/'Tenkaichi3Decomp-WiiLocal-r17-Lobby013'
def hashes(path):return {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in path.glob('*.o')}
before=hashes(base/'port/build/obj_win64')
log=''
for name,obj in [('ui.cpp','cxx_ui'),('online_lobby.cpp','cxx_online_lobby'),('net_update.c','gs_net_update')]:
    cpp=name.endswith('.cpp')
    cmd=['g++' if cpp else 'gcc','-m32','-std=c++17' if cpp else '-std=gnu99','-c','-O2','-g','-fno-pic','-msse2','-mfpmath=sse']
    cmd+=['-fno-exceptions','-fno-rtti','-w'] if cpp else ['-fno-strict-aliasing','-Wall','-Wno-unused','-Wno-misleading-indentation']
    cmd+=['-Iport/third_party/imgui','-Iport/src/gs','-Iport/src','-Iport/build/gen/gs',str(b.ROOT/'port/src/gs'/name),'-o',str(b.undefined.OBJ/(obj+'.o'))]
    r=b.undefined.run(cmd,cwd=b.ROOT,capture_output=True,text=True)
    log+=name+'\n'+r.stdout+r.stderr
    (b.ROOT/'port/build/lobby18-compile.log').write_text(log,'utf-8')
    assert r.returncode==0,r.stderr
    print('Compiled',name,flush=True)
for name in ['btl_seq.c','hud_0.c']:
    obj,file,error,pending=b.cc(b.ROOT/'src/battle'/name)
    log+=name+'\n'+error
    (b.ROOT/'port/build/lobby18-compile.log').write_text(log,'utf-8')
    assert obj,error
    print('Compiled',name,flush=True)
after=hashes(b.undefined.OBJ)
changed=sorted(n for n in before if before[n]!=after[n])
assert changed==sorted(['cxx_ui.o','cxx_online_lobby.o','gs_net_update.o','battle_btl_seq.o','battle_hud_0.o']),changed
assert hashes(base/'port/build/obj_data_win64')==hashes(b.ROOT/'port/build/obj_data_win64')
output=io.StringIO()
with contextlib.redirect_stdout(output):import link
text=output.getvalue()
(b.ROOT/'port/build/lobby18-link.log').write_text(text,'utf-8')
assert 'link OK' in text,text
(b.ROOT/'port/build/lobby18-objects.json').write_text(json.dumps({'changed_objects':changed,'before':before,'after':after},indent=2)+'\n','utf-8')
print(text,flush=True)
