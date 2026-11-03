from pathlib import Path
import os
import subprocess
root = Path(__file__).resolve().parents[2]
source = Path(os.environ.get('DOLPHIN_10912', r'D:\dolphin-82fd7f576e1dff6b616ff088955c18aa76ed45d5'))
out = root / 'port/build/local-tests'
out.mkdir(parents=True, exist_ok=True)
vendor = (root / 'port/third_party/dolphin').as_posix()
for suffix in ('.cpp', '.h'):
    text = (source / 'Source/Core/InputCommon/ControlReference' / ('ExpressionParser' + suffix)).read_text()
    text = text.replace('namespace ciface::ExpressionParser', 'namespace ciface::OriginalParser')
    text = text.replace('"InputCommon/ControlReference/ExpressionParser.h"', '"original.h"')
    text = text.replace('"Common/StringUtil.h"', f'"{vendor}/Common/StringUtil.h"')
    text = text.replace('"InputCommon/ControllerInterface/Device.h"', f'"{vendor}/InputCommon/ControllerInterface/Device.h"')
    (out / ('original' + suffix)).write_text(text)
env = os.environ.copy()
env['PATH'] = r'E:\BT3-Wii-tools\mingw64\bin;' + env['PATH']
exe = out / 'parser-parity.exe'
subprocess.run([r'E:\BT3-Wii-tools\mingw64\bin\g++.exe', '-std=c++17', '-O2', 'local/tests/parser_parity.cpp', '-o', str(exe)], cwd=root, env=env, check=True)
subprocess.run([str(exe)], cwd=root, env=env, check=True)
