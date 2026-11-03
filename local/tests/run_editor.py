from pathlib import Path
import os, subprocess
root = Path(__file__).resolve().parents[2]
cc = Path(r'E:\BT3-Wii-tools\mingw64\bin\g++.exe')
out = root / 'port/build/local-tests/editor.exe'
env = os.environ.copy()
env['PATH'] = str(cc.parent) + r';E:\BT3-Wii-tools\ucrt64\bin;' + env['PATH']
env.update(BT3_SETTINGS='', SDL_VIDEODRIVER='dummy')
imgui = 'port/third_party/imgui/'
sources = ['local/tests/test_editor.cpp', 'port/src/gs/control_bindings.cpp'] + [imgui + f for f in ('imgui.cpp','imgui_draw.cpp','imgui_tables.cpp','imgui_widgets.cpp')]
subprocess.run([str(cc), '-std=c++17', '-O1', '-w', '-I' + imgui, '-IE:/BT3-Wii-tools/ucrt64/include', *sources, '-LE:/BT3-Wii-tools/ucrt64/lib', '-lSDL3', '-lwinpthread', '-o', str(out)], cwd=root, env=env, check=True)
subprocess.run([str(out)], cwd=root, env=env, check=True)
