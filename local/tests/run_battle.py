from pathlib import Path
import os
import subprocess
root = Path(__file__).resolve().parents[2]
out = root / 'port/build/local-tests'
out.mkdir(parents=True, exist_ok=True)
env = os.environ.copy()
env['PATH'] = r'E:\BT3-Wii-tools\mingw64\bin;' + env['PATH']
exe = out / 'battle.exe'
cmd = [r'E:\BT3-Wii-tools\mingw64\bin\gcc.exe', '-std=gnu99', '-O2', '-ffunction-sections', '-fdata-sections', '-fno-builtin', '-fcommon', '-w',
       '-Iinclude', '-Iport/include', '-include', 'port_compat.h', 'local/tests/test_battle.c',
       'src/battle/btl_input.c', 'src/sys/game_pad.c', 'src/sys/pad.c', '-Wl,--gc-sections', '-lm', '-o', str(exe)]
subprocess.run(cmd, cwd=root, env=env, check=True)
subprocess.run([str(exe)], cwd=root, env=env, check=True)
