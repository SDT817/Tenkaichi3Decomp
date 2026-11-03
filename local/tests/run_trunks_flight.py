"""Compile the real handler/input and extract the unchanged Main decision table."""
from pathlib import Path
import os
import re
import subprocess

root = Path(__file__).resolve().parents[2]
out = root / 'port/build/local-tests'
out.mkdir(parents=True, exist_ok=True)
source = (root / 'src/battle/btl_act_h_b.c').read_text('utf-8')
def extract(text, name):
    m = re.search(r'^[A-Za-z_][^\n;{}]*\b' + name + r'\([^\n;{}]*\) \{', text, re.M)
    assert m, name
    return text[m.start():text.index('\n}\n', m.end()) + 3]

start = source.index('s32 BtlDecide_Main(')
end = source.index('\n}\n', start) + 3
function = source[start:end]
names = set(re.findall(r'\b(Btl\w+)\(', function)) - {'BtlDecide_Main'}
prototypes = ['extern s32 BtlInput_TestAction(BtlActIChr *, s32, s32);']
for name in sorted(names):
    found = re.search(r'^extern ([^;\n]*\b' + name + r'\([^;\n]*\));', source, re.M)
    if found:
        prototypes.append('extern ' + found[1] + ';')
    else:
        # These declarations are cast macros in the combined upstream source.
        sig = {'BtlChar_TestFlag': 's32 BtlChar_TestFlag(BtlActIChr *, s32)',
               'BtlOpp_GetSeenAction': 's32 BtlOpp_GetSeenAction(BtlActIChr *)',
               'BtlAct_GetCurrent': 's32 BtlAct_GetCurrent(BtlActIChr *)',
               'BtlParam_GetFlags': 's32 BtlParam_GetFlags(BtlActIChr *)'}[name]
        prototypes.append('extern ' + sig + ';')
unit = out / 'trunks_decide.c'
unit.write_text('#include "common.h"\n#include "battle/btl_act_i.h"\n' +
                '\n'.join(prototypes) + '\n#define TEST(id) BtlInput_TestAction(chr, id, 1)\n' + function, 'utf-8')
neutral = (root / 'src/battle/btl_act_d.c').read_text('utf-8')
parent_neutral = (root.parent / 'Tenkaichi3Decomp-WiiLocal-r20-Lobby016/src/battle/btl_act_d.c').read_text('utf-8')
assert extract(neutral, 'BtlAct_DashMoveHandler') == extract(parent_neutral, 'BtlAct_DashMoveHandler'), 'Original flight handler changed'
begin_frame = extract((root / 'src/battle/btl_char_mgr.c').read_text('utf-8'), 'BtlChar_BeginFrame')
assert 'chr->prevAction = chr->action;' in begin_frame, 'Recheck previous-action snapshot lifecycle'
neutral_unit = out / 'trunks_neutral.c'
decl = re.findall(r'^extern [^;]+;', neutral, re.M)
movement_functions = ('BtlAct_NeutralHandler', 'BtlAct_MoveHandler', 'BtlAct_CloseMoveHandler')
neutral_unit.write_text('#include "common.h"\n#include "battle/btl_act_d.h"\n' +
                       '\n'.join(decl) + '\n#define BTL_KMH(x) ((x)*1000.0f/3600.0f*(1.0f/30.0f))\n' +
                       '#define BTL_DEG(x) ((x)/180.0f*3.14159265f)\n' +
                       '#define PHASE_ENTER 0\n#define PHASE_RUN 1\n#define PHASE_DECIDE 2\n#define PHASE_LEAVE 3\n' +
                       extract(neutral, 'BtlAct_TrunksFlightMask') + '\n' +
                       '\n'.join(extract(neutral, name) for name in movement_functions), 'utf-8')
dispatcher = (root / 'src/battle/btl_char_action.c').read_text('utf-8')
dispatcher_unit = out / 'trunks_dispatcher.c'
dispatcher_unit.write_text('#include "common.h"\n#include "battle/btl_char_action.h"\n' +
                          '\n'.join(re.findall(r'^extern [^;]+;', dispatcher, re.M)) + '\n' +
                          extract(dispatcher, 'BtlAct_Update'), 'utf-8')
inputs = (root / 'src/battle/btl_input.c').read_text('utf-8')
input_unit = out / 'trunks_input_queries.c'
needed, pending = set(), ['BtlInput_TestAction']
while pending:
    name = pending.pop()
    if name in needed:
        continue
    needed.add(name)
    fn = extract(inputs, name)
    pending += list(set(re.findall(r'\b(BtlInput_\w+)\(', fn)) - needed)
definitions = sorted((inputs.index(extract(inputs, name)), name) for name in needed)
input_unit.write_text(inputs[:inputs.index('u8 BtlInput_StickToByte(')] +
                      '\n'.join(extract(inputs, name) for _, name in definitions), 'utf-8')
env = os.environ.copy()
env['PATH'] = r'E:\BT3-Wii-tools\mingw64\bin;' + env['PATH']
exe = out / 'trunks_flight.exe'
cmd = [r'E:\BT3-Wii-tools\mingw64\bin\gcc.exe', '-std=gnu99', '-O2',
       '-ffunction-sections', '-fdata-sections', '-fno-builtin', '-fcommon', '-w',
       '-Iinclude', '-Iport/include', '-include', 'port_compat.h',
       'local/tests/test_trunks_flight.c', str(input_unit.relative_to(root)),
       str(neutral_unit.relative_to(root)), str(unit.relative_to(root)), str(dispatcher_unit.relative_to(root)),
       '-Wl,--gc-sections', '-lm', '-o', str(exe.relative_to(root))]
subprocess.run(cmd, cwd=root, env=env, check=True)
subprocess.run([str(exe)], cwd=root, env=env, check=True)
