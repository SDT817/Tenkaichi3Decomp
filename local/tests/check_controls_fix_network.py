"""Verify the new official network sources/objects and all online UI statements."""
from pathlib import Path
import hashlib
import json
import re
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'local'))
from merge_controls_fix import snapshot, UPSTREAM, normalized
import build_windows as build

def online_tokens(source):
    text = source[source.index('static void quick_status('):source.index('void Ui_Toggle(')]
    text = text.replace('UiZh(Port_LobbyError())', 'Port_LobbyError()')
    token = re.compile(r'//[^\n]*|/\*.*?\*/|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'', re.S)
    text = token.sub(lambda m: '"text"' if m.group().startswith('"') else m.group() if m.group().startswith("'") else '', text)
    return re.sub(r'\s+', '', text)

def main():
    official = snapshot(UPSTREAM)
    names = [n for n in official if n.startswith(('port/matchmaking/', 'port/src/gs/net')) or n in {
        'port/src/gs/state.c', 'port/src/plat_stub.c', 'src/sys/pad.c', 'port/src/plat_fprint.c'}]
    hashes = {}
    for name in names:
        data = normalized((ROOT / name).read_bytes())
        assert data == official[name], name
        hashes[name] = hashlib.sha256(data).hexdigest()
    assert 'NET_VERSION = 5' in (ROOT / 'port/src/gs/net.c').read_text(encoding='utf-8')
    assert online_tokens(official['port/src/gs/ui.cpp'].decode()) == online_tokens((ROOT / 'port/src/gs/ui.cpp').read_text(encoding='utf-8'))
    baseline = ROOT / 'port/build/official-network-0.1.38.9'
    baseline.mkdir(exist_ok=True)
    objects = {}
    with tempfile.TemporaryDirectory(prefix='bt3-net-official-') as temp:
        source = Path(temp)
        for name, data in official.items():
            if name.startswith(('port/src/', 'port/include/', 'include/')):
                p = source / name; p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(data)
        for file in sorted((source / 'port/src/gs').glob('net*.c')):
            obj = baseline / ('gs_' + file.stem + '.o')
            key = build.undefined.buildkey.flags() if file.name == 'net_sign.c' else []
            result = build.undefined.run(['gcc', '-m32', '-std=gnu99', '-c', '-O2', '-g', '-fno-pic',
                '-msse2', '-mfpmath=sse', '-fno-strict-aliasing', '-Wall', '-Wno-unused', '-Wno-misleading-indentation',
                '-Iport/build/gen/gs', *key, str(file), '-o', str(obj)], cwd=ROOT, capture_output=True, text=True)
            assert result.returncode == 0, result.stderr
            blobs = []
            for i, path in enumerate((obj, ROOT / 'port/build/obj_win64' / obj.name)):
                stripped = source / f'{i}.o'
                subprocess.run([str(build.TOOLS / 'mingw64/bin/objcopy.exe'), '--strip-debug', str(path), str(stripped)], check=True)
                blobs.append(stripped.read_bytes())
            assert blobs[0] == blobs[1], obj.name
            objects[obj.name] = hashlib.sha256(blobs[0]).hexdigest()
    assert len(objects) == 6
    report = {'official_base': UPSTREAM, 'official_version': '0.1.38.9', 'protocol': 5,
              'exact_official_sources': hashes, 'online_ui_nontext_tokens_identical': True,
              'network_objects_identical_without_debug': objects, 'remote_UU_test': 'not performed'}
    (ROOT / 'records/network-checks.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'PASS: {len(hashes)} protected sources and all six network objects match official 0.1.38.9; online UI statements unchanged; protocol 5')

if __name__ == '__main__':
    main()
