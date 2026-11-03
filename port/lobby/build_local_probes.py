"""Compile headless probes using the game's compiler and exact ImGui objects."""
from pathlib import Path
import os
import sys
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'local'))
import build_windows as build
OUT = ROOT.parent/'Chinese-local-analysis-20261022/online-lobby8-v014-20261030/verification'

for cpp, name in [(True, 'ui_local_probe'), (False, 'present_mode_probe')]:
    cmd = ['g++' if cpp else 'gcc', '-m32', '-std=c++17' if cpp else '-std=gnu99', '-O2',
           '-fwhole-program', '-ffunction-sections', '-fdata-sections', '-Iport/src/gs', '-Iport/build/gen/gs', '-Iport/third_party/imgui',
           'port/lobby/'+name+('.cpp' if cpp else '.c')]
    if cpp:
        cmd += ['-fno-exceptions', '-fno-rtti']
        cmd += [str(build.undefined.OBJ/(n+'.o')) for n in ['cxx_imgui', 'cxx_imgui_draw', 'cxx_imgui_widgets', 'cxx_imgui_tables']]
    cmd += ['-Wl,--gc-sections,--exclude-all-symbols', '-o', os.path.relpath(OUT/(name+'.exe'), ROOT),
            '-LE:/BT3-Wii-tools/ucrt64/lib', '-lSDL3', '-lm']
    result = build.undefined.run(cmd, cwd=ROOT, capture_output=True)
    (OUT/(name+'-build.log')).write_bytes(result.stdout+result.stderr)
    assert result.returncode == 0, result.stderr.decode('utf-8', 'replace')[-5000:]
    print('Built', name, flush=True)
