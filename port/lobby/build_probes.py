"""Use the same Windows compiler/SDL flags as the game, with a separate main."""
from pathlib import Path
import sys
import os
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'local'))
import build_windows as build
OUT=Path(os.environ.get('BT3_PROBE_OUT',ROOT.parent/'Chinese-local-analysis-20261022/online-lobby10-v016-20261101/verification'))
OUT.mkdir(parents=True,exist_ok=True)
flags=['-m32','-std=gnu99','-O2','-Iport/src/gs','-Iport/build/gen/gs']
for name,sources in [('client_probe',['port/lobby/client_probe.c','port/src/gs/net_match.c','port/src/gs/net_sign.c','port/src/gs/net_relay.c'])]:
    import os
    cmd=['gcc',*flags,*sources,'-o',os.path.relpath(OUT/(name+'.exe'),ROOT),'-LE:/BT3-Wii-tools/ucrt64/lib','-lSDL3','-lwinhttp','-lws2_32','-lm']
    run=build.undefined.run(cmd,cwd=ROOT,capture_output=True,text=True)
    if run.returncode:raise RuntimeError(run.stderr)
    print('Built',name,flush=True)
for probe in ('lobby_probe','settings_probe'):
    cmd=['g++','-m32','-std=c++17','-O2','-fno-exceptions','-fno-rtti',
     '-Iport/third_party/imgui','-Iport/src/gs','-Iport/build/gen/gs',
     'port/lobby/'+probe+'.cpp',
     *[str(build.undefined.OBJ/(n+'.o')) for n in ['gs_update_sign','gs_net_match','gs_net_sign','gs_net_relay','cxx_online_ping','cxx_imgui','cxx_imgui_draw','cxx_imgui_widgets','cxx_imgui_tables']],
     '-o',os.path.relpath(OUT/(probe+'.exe'),ROOT),'-LE:/BT3-Wii-tools/ucrt64/lib','-lSDL3','-lwinhttp','-lws2_32','-lm']
    run=build.undefined.run(cmd,cwd=ROOT,capture_output=True,text=True)
    if run.returncode:raise RuntimeError(run.stderr)
    print('Built headless',probe,flush=True)
cmd=['gcc',*flags,'port/lobby/relay_probe.c','-o',os.path.relpath(OUT/'relay_probe.exe',ROOT),
     '-LE:/BT3-Wii-tools/ucrt64/lib','-lSDL3','-lws2_32','-lm']
run=build.undefined.run(cmd,cwd=ROOT,capture_output=True,text=True)
if run.returncode:raise RuntimeError(run.stderr)
print('Built TURN wire probe',flush=True)
