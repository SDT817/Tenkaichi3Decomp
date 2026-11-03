"""Fail if this local edition changes any official networking/protocol source."""
from pathlib import Path
import hashlib
import json
import subprocess
import tempfile
import io
import tarfile
import sys
import re

root = Path(__file__).resolve().parents[2]
base = '11059a6d3e814cf36e6ca1f6307839f61c56f1cc'
def git(*args): return subprocess.check_output(['git', *args], cwd=root)
files = [name for name in git('ls-files').decode().splitlines()
         if name.startswith(('port/matchmaking/', 'port/src/gs/net')) or name in {
             'port/src/gs/state.c', 'port/src/plat_stub.c', 'src/battle/btl_seq.c', 'src/sys/pad.c',
             'port/src/gs/gs_core.c', 'port/src/gs/snd_se.c', 'port/src/plat_crash.c',
             'port/src/plat_fprint.c', 'src/battle/eft_aa.c'}]
report = {'official_base': base, 'protocol': 5, 'sources': {}, 'objects_without_debug': {}}
# UI strings may be translated; the online window's non-text statements and
# API arguments must remain upstream's. The one adapter only translates errors.
def net_ui_tokens(source):
    text = source[source.index('static void quick_status('):source.index('void Ui_Toggle(')]
    text = text.replace('UiZh(Port_LobbyError())', 'Port_LobbyError()')
    token = re.compile(r'//[^\n]*|/\*.*?\*/|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'', re.S)
    text = token.sub(lambda m: '"text"' if m.group().startswith('"') else m.group() if m.group().startswith("'") else '', text)
    return re.sub(r'\s+', '', text)
ui_base = git('show', f'{base}:port/src/gs/ui.cpp').decode('utf-8')
ui_local = (root / 'port/src/gs/ui.cpp').read_text(encoding='utf-8')
assert net_ui_tokens(ui_base) == net_ui_tokens(ui_local), 'Online UI changed beyond display strings'
report['online_ui_non_text_tokens_identical'] = True
for name in files:
    original = git('show', f'{base}:{name}')
    actual = (root / name).read_bytes().replace(b'\r\n', b'\n')
    assert original == actual, f'Networking source changed: {name}'
    report['sources'][name] = hashlib.sha256(actual).hexdigest()
assert b'NET_VERSION = 5' in (root / 'port/src/gs/net.c').read_bytes()
sys.path.insert(0, str(root / 'local'))
import build_windows as build
baseline = root / 'port/build/official-baseline'
baseline.mkdir(parents=True, exist_ok=True)
with tempfile.TemporaryDirectory(prefix='bt3-net-base-') as temp:
    snapshot = Path(temp)
    with tarfile.open(fileobj=io.BytesIO(git('archive', base, 'port/src', 'port/include', 'include'))) as archive:
        archive.extractall(snapshot, filter='data')
    for source in sorted((snapshot / 'port/src/gs').glob('net*.c')):
        output = baseline / ('gs_' + source.stem + '.o')
        key = build.undefined.buildkey.flags() if source.name == 'net_sign.c' else []
        result = build.undefined.run(['gcc', '-m32', '-std=gnu99', '-c', '-O2', '-g', '-fno-pic',
                  '-msse2', '-mfpmath=sse', '-fno-strict-aliasing', '-Wall', '-Wno-unused',
                  '-Wno-misleading-indentation', '-Iport/build/gen/gs', *key, str(source), '-o', str(output)],
                  cwd=root, capture_output=True, text=True)
        if result.returncode:
            raise RuntimeError(result.stderr)
with tempfile.TemporaryDirectory(prefix='bt3-net-check-') as temp:
    for original in sorted(baseline.glob('gs_net*.o')):
        blobs = []
        for index, obj in enumerate((original, root / 'port/build/obj_win64' / original.name)):
            out = Path(temp) / f'{index}.o'
            subprocess.run([r'E:\BT3-Wii-tools\mingw64\bin\objcopy.exe', '--strip-debug', str(obj), str(out)], check=True)
            blobs.append(out.read_bytes())
        assert blobs[0] == blobs[1], f'Network machine code changed: {original.name}'
        report['objects_without_debug'][original.name] = hashlib.sha256(blobs[0]).hexdigest()
assert len(report['objects_without_debug']) == 5
out = root / 'port/build/network-invariants.json'
out.write_text(json.dumps(report, indent=2) + '\n')
print(f'PASS: {len(files)} official networking sources unchanged; protocol 5; all five network objects identical after removing build-path debug info')
