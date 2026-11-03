from pathlib import Path
import os
import sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'local'))
import build_windows as b
OUT=ROOT.parent/'Chinese-local-analysis-20261022/online-lobby8-v014-20261030/verification'
cmd=['gcc','-m32','-std=gnu99','-O2','-ffunction-sections','-fdata-sections','-Wl,--gc-sections',
     '-Iport/src/gs','-Iport/build/gen/gs','port/lobby/wire_probe.c',
     'port/src/gs/net_match.c','port/src/gs/net_relay.c','port/src/gs/net_sign.c',
     'port/src/gs/net_lobby.c','port/src/gs/net_chat.c',
     '-o',os.path.relpath(OUT/'wire_probe.exe',ROOT),'-LE:/BT3-Wii-tools/ucrt64/lib','-lSDL3','-lwinhttp','-lws2_32','-lm']
r=b.undefined.run(cmd,cwd=ROOT,capture_output=True,text=True)
(OUT/'wire-build.log').write_text(r.stdout+r.stderr,'utf-8')
if r.returncode:raise RuntimeError(r.stderr)
print('Built actual upstream handshake probe')
