"""Build only the lobby UI, translator, renderer capture and private version."""
import contextlib
import hashlib
import io
import json
import build_windows as b

base=b.ROOT.parent/'Tenkaichi3Decomp-WiiLocal-r18-Lobby014'
def hashes(path):return {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in path.glob('*.o')}
before=hashes(base/'port/build/obj_win64')
log=''
changed_sources=[('ui.cpp','cxx_ui'),('online_lobby.cpp','cxx_online_lobby'),
                 ('ui_text_translate.c','gs_ui_text_translate'),('gs_draw.c','gs_gs_draw'),
                 ('net_update.c','gs_net_update')]
for name,obj in changed_sources:
    cpp=name.endswith('.cpp')
    cmd=['g++' if cpp else 'gcc','-m32','-std=c++17' if cpp else '-std=gnu99','-c','-O2','-g','-fno-pic','-msse2','-mfpmath=sse']
    cmd+=['-fno-exceptions','-fno-rtti','-w'] if cpp else ['-fno-strict-aliasing','-Wall','-Wno-unused','-Wno-misleading-indentation']
    cmd+=['-Iport/third_party/imgui','-Iport/src/gs','-Iport/src','-Iport/build/gen/gs',str(b.ROOT/'port/src/gs'/name),'-o',str(b.undefined.OBJ/(obj+'.o'))]
    r=b.undefined.run(cmd,cwd=b.ROOT,capture_output=True,text=True)
    log+=name+'\n'+r.stdout+r.stderr
    (b.ROOT/'port/build/lobby19-compile.log').write_text(log,'utf-8')
    assert r.returncode==0,r.stderr
    print('Compiled',name,flush=True)
after=hashes(b.undefined.OBJ)
changed=sorted(n for n in before if before[n]!=after[n])
assert changed==sorted(obj+'.o' for name,obj in changed_sources),changed
assert hashes(base/'port/build/obj_data_win64')==hashes(b.ROOT/'port/build/obj_data_win64')
output=io.StringIO()
with contextlib.redirect_stdout(output):import link
text=output.getvalue()
(b.ROOT/'port/build/lobby19-link.log').write_text(text,'utf-8')
assert 'link OK' in text,text
(b.ROOT/'port/build/lobby19-objects.json').write_text(json.dumps({'changed_objects':changed,'before':before,'after':after},indent=2)+'\n','utf-8')
print(text,flush=True)
