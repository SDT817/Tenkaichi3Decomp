from pathlib import Path
import os
import subprocess
import tempfile

root = Path(__file__).resolve().parents[2]
out = root / 'port/build/local-tests'
out.mkdir(parents=True, exist_ok=True)
tools = Path(r'E:\BT3-Wii-tools')
env = dict(os.environ)
env['PATH'] = str(tools / 'mingw64/bin') + ';' + str(root / 'port/build/qa-local/Tenkaichi3Decomp') + ';' + env['PATH']
common = ['-O1', '-w', '-ffunction-sections', '-fdata-sections', '-Iport/third_party/imgui', '-Iport/src/gs', '-IE:/BT3-Wii-tools/ucrt64/include']
imgui = 'port/third_party/imgui/'
sources = ['local/tests/test_bindings.c', 'port/src/plat_settings.c', 'port/src/gs/control_bindings.cpp',
           'port/src/gs/control_profiles.cpp', 'local/tests/test_profile_ui.cpp']
sources += [imgui + f for f in ('imgui.cpp', 'imgui_draw.cpp', 'imgui_tables.cpp', 'imgui_widgets.cpp')]
objects = []
for source in sources:
    obj = out / ('profile_ui_' + Path(source).stem + '.o')
    compiler = tools / ('mingw64/bin/gcc.exe' if source.endswith('.c') else 'mingw64/bin/g++.exe')
    flags = ['-Dmain=Bindings_OriginalMain'] if source.endswith('test_bindings.c') else []
    subprocess.run([str(compiler), '-c', *common, *flags, source, '-o', str(obj)], cwd=root, env=env, check=True)
    objects.append(str(obj))
exe = out / 'profile-ui.exe'
subprocess.run([str(tools / 'mingw64/bin/g++.exe'), *objects, str(tools / 'mingw64/lib/libz.a'),
                '-LE:/BT3-Wii-tools/ucrt64/lib', '-Wl,--gc-sections', '-lSDL3', '-lwinpthread', '-o', str(exe)], cwd=root, env=env, check=True)
with tempfile.TemporaryDirectory(prefix='bt3-profile-ui-') as temp:
    folder = Path(temp)
    settings = folder / 'settings.txt'; settings.write_text('')
    fixture = folder / 'partial.ini'; fixture.write_text('[Profile]\nButtons/A=`unknown key`\nButtons/Start=GRAVE\n')
    env.update(BT3_SETTINGS=str(settings), BT3_TEST_PARTIAL=str(fixture), SDL_VIDEODRIVER='dummy')
    subprocess.run([str(exe)], cwd=root, env=env, check=True)
