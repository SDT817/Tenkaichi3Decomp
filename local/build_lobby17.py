"""Rebuild only changed r16 objects, preserving all CN8 data and other objects."""
import contextlib
import io
import json
import hashlib
import build_windows as b

base = b.ROOT.parent/'Tenkaichi3Decomp-WiiLocal-r16-CN8-Lobby'
def hashes(path):
    return {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in path.glob('*.o')}
before = hashes(base/'port/build/obj_win64')
log = ''
for folder, name, obj in [('gs','ui.cpp','cxx_ui'), ('gs','online_lobby.cpp','cxx_online_lobby'),
                          ('gs','net.c','gs_net'), ('gs','net_update.c','gs_net_update')]:
    cpp = name.endswith('.cpp')
    cmd = ['g++' if cpp else 'gcc','-m32','-std=c++17' if cpp else '-std=gnu99',
           '-c','-O2','-g','-fno-pic','-msse2','-mfpmath=sse']
    cmd += ['-fno-exceptions','-fno-rtti','-w'] if cpp else ['-fno-strict-aliasing','-Wall','-Wno-unused','-Wno-misleading-indentation']
    cmd += ['-Iport/third_party/imgui','-Iport/src/gs','-Iport/src','-Iport/build/gen/gs',
            str(b.ROOT/'port/src'/folder/name),'-o',str(b.undefined.OBJ/(obj+'.o'))]
    r = b.undefined.run(cmd,cwd=b.ROOT,capture_output=True,text=True)
    log += name+'\n'+r.stdout+r.stderr
    (b.ROOT/'port/build/lobby17-compile.log').write_text(log,'utf-8')
    assert r.returncode == 0, r.stderr
    print('Compiled',name,flush=True)
cmd = ['gcc','-m32','-std=gnu99','-c','-O2','-g','-fno-pic','-malign-double','-fno-strict-aliasing',
       '-ffp-contract=off','-fno-builtin','-w','-Iinclude','-Iport/include','-Iport/src',
       '-msoft-float','-mno-sse','-mno-mmx','-DSF_FAST_CALLS','-include','math.h','-include','stdlib.h','-include','port_libm.h']
r=b.undefined.compile_ee(cmd,b.ROOT/'port/src/a11y_game.c',b.undefined.OBJ/'pc_a11y_game.o')
assert r.returncode == 0,r.stderr
print('Compiled a11y_game.c',flush=True)
obj, file, error, pending = b.cc(b.ROOT/'src/battle/btl_cam.c')
assert obj, error
print('Compiled btl_cam.c',flush=True)
after = hashes(b.undefined.OBJ)
changed = sorted(n for n in before if before[n] != after[n])
assert changed == sorted(['cxx_ui.o','cxx_online_lobby.o','gs_net.o','gs_net_update.o','pc_a11y_game.o','battle_btl_cam.o']),changed
assert hashes(base/'port/build/obj_data_win64') == hashes(b.ROOT/'port/build/obj_data_win64')
output=io.StringIO()
with contextlib.redirect_stdout(output):
    import link
text=output.getvalue()
(b.ROOT/'port/build/lobby17-link.log').write_text(text,'utf-8')
assert 'link OK' in text,text
(b.ROOT/'port/build/lobby17-objects.json').write_text(json.dumps({'changed_objects':changed,'before':before,'after':after},indent=2)+'\n','utf-8')
print(text,flush=True)
