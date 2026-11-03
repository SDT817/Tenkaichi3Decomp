from pathlib import Path
import ctypes
import os
import subprocess
import tempfile

root = Path(__file__).resolve().parents[2]
ctypes.windll.kernel32.SetErrorMode(0x8003) # Keep test crashes in the runner, without desktop error dialogs.
out = root / 'port/build/local-tests'
out.mkdir(parents=True, exist_ok=True)
env = os.environ.copy()
env['PATH'] = str(root / 'port/build/qa-local/Tenkaichi3Decomp') + ';' + r'E:\BT3-Wii-tools\mingw64\bin;' + env['PATH']
cc = r'E:\BT3-Wii-tools\mingw64\bin\gcc.exe'
cpp = r'E:\BT3-Wii-tools\mingw64\bin\g++.exe'
common = ['-O2', '-w', '-ffunction-sections', '-fdata-sections', '-Iport/src/gs', '-IE:/BT3-Wii-tools/ucrt64/include']
objects = []
for source, compiler in [('local/tests/test_bindings.c', cc), ('port/src/plat_settings.c', cc),
                         ('port/src/gs/control_bindings.cpp', cpp), ('port/src/gs/control_profiles.cpp', cpp),
                         ('local/tests/test_profiles.cpp', cpp)]:
    obj = out / ('profile_' + Path(source).stem + '.o')
    flags = ['-Dmain=Bindings_OriginalMain'] if source.endswith('test_bindings.c') else []
    subprocess.run([compiler, '-c', *common, *flags, source, '-o', str(obj)], cwd=root, env=env, check=True)
    objects.append(str(obj))
exe = out / 'profiles.exe'
subprocess.run([cpp, *objects, 'E:/BT3-Wii-tools/mingw64/lib/libz.a', '-LE:/BT3-Wii-tools/ucrt64/lib', '-Wl,--gc-sections', '-lSDL3', '-lwinpthread', '-lm', '-o', str(exe)], cwd=root, env=env, check=True)
env['SDL_VIDEODRIVER'] = 'dummy'
env.setdefault('BT3_TEST_DOLPHIN', r'C:\Users\Admin\AppData\Roaming\Dolphin Emulator\Config\Profiles\GCPad\1.ini')
with tempfile.TemporaryDirectory(prefix='wii-profiles-') as temp:
    settings = Path(temp) / 'settings.txt'
    settings.write_text('')
    env['BT3_SETTINGS'] = str(settings)
    for key, folder in [('APPDATA', 'appdata'), ('BT3_TEST_DOCUMENTS', '文档')]:
        env[key] = str(Path(temp) / folder)
        preset = Path(env[key]) / 'Dolphin Emulator/Config/Profiles/GCPad/Same.ini'
        preset.parent.mkdir(parents=True)
        preset.write_text('[Profile]\nDevice=DInput/0/Keyboard Mouse\nButtons/A=J\n')
    subprocess.run([str(exe)], cwd=root, env=env, check=True, timeout=60)
    stored = list((Path(temp) / 'wii_profiles').glob('*.ini'))
    assert len(stored) == 1
    assert 'Action7/Range = -250' in stored[0].read_text(encoding='utf-8')
