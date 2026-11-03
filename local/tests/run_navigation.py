from pathlib import Path
import os, subprocess
root = Path(__file__).resolve().parents[2]
cc = Path(r'E:\BT3-Wii-tools\mingw64\bin\g++.exe')
out = root / 'port/build/local-tests/navigation.exe'
env = os.environ.copy(); env['PATH'] = str(cc.parent) + ';' + env['PATH']
imgui = 'port/third_party/imgui/'
sources = ['local/tests/test_navigation.cpp'] + [imgui + f for f in ('imgui.cpp','imgui_draw.cpp','imgui_tables.cpp','imgui_widgets.cpp')]
result = subprocess.run([str(cc), '-std=c++17', '-flto', '-fwhole-program', '-O2', '-w', '-ffunction-sections', '-fdata-sections', '-Wl,--gc-sections', '-I' + imgui, '-IE:/BT3-Wii-tools/ucrt64/include', '-Iport/build/gen/gs', *sources, '-o', str(out)], cwd=root, env=env, capture_output=True, text=True)
if result.returncode: raise RuntimeError(result.stderr[:3000])
subprocess.run([str(out)], cwd=root, env=env, check=True)
