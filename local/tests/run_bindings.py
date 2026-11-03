from pathlib import Path
import os
import subprocess
import tempfile

root = Path(__file__).resolve().parents[2]
out = root / 'port/build/local-tests'
out.mkdir(parents=True, exist_ok=True)
env = os.environ.copy()
env['PATH'] = r'E:\BT3-Wii-tools\mingw64\bin;E:\PS2 yizhi\Tenkaichi3Decomp-windows-x64\Tenkaichi3Decomp;' + env['PATH']
cc = r'E:\BT3-Wii-tools\mingw64\bin\gcc.exe'
cpp = r'E:\BT3-Wii-tools\mingw64\bin\g++.exe'
common = ['-O2', '-w', '-ffunction-sections', '-fdata-sections', '-Iport/src/gs', '-IE:/BT3-Wii-tools/ucrt64/include']
objects = []
for source, compiler in [('local/tests/test_bindings.c', cc), ('port/src/plat_settings.c', cc), ('port/src/gs/control_bindings.cpp', cpp)]:
    obj = out / (Path(source).stem + '.o')
    subprocess.run([compiler, '-c', *common, source, '-o', str(obj)], cwd=root, env=env, check=True)
    objects.append(str(obj))
exe = out / 'bindings.exe'
subprocess.run([cpp, *objects, '-LE:/BT3-Wii-tools/ucrt64/lib', '-Wl,--gc-sections', '-lSDL3', '-lwinpthread', '-lm', '-o', str(exe)], cwd=root, env=env, check=True)
env['SDL_VIDEODRIVER'] = 'dummy'
with tempfile.TemporaryDirectory(prefix='wii-bindings-') as temp:
    settings = Path(temp) / '配置测试.txt'
    settings.write_text('key_p1_cross=20\nkey_p2_cross=21\n', encoding='utf-8')
    env['BT3_SETTINGS'] = str(settings)
    for action in ('write', 'reload', 'input'):
        subprocess.run([str(exe), action], cwd=root, env=env, check=True)

with tempfile.TemporaryDirectory(prefix='wii-migrate-') as temp:
    settings = Path(temp) / 'settings.txt'
    settings.write_text('')
    expr = Path(str(settings) + '.wii.ini')
    old = '# Dolphin expressions: player.profile.column.action=range:expression\n0.1.0.7=100:J | (K & !L)\n0.1.1.7=100:A & `Left trigger`\n1.1.0.26=100:\n1.1.1.26=75:`Right trigger`\n'
    expr.write_text(old)
    env['BT3_SETTINGS'] = str(settings)
    subprocess.run([str(exe), 'migration'], cwd=root, env=env, check=True)
    assert Path(str(expr) + '.r1.bak').read_text() == old
    assert '# Wii unified expressions v2' in expr.read_text()
    assert '1.1.26=75:`Controller:Right trigger`' in expr.read_text()
    print('PASS migration: original bytes backed up before saving unified v2')
