"""Verify CN3 source boundaries, unchanged networking objects and deployed files."""
from pathlib import Path
import hashlib
import json
import os
import re
import struct
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]
CN2 = ROOT.parent / 'Tenkaichi3Decomp-WiiLocal-r5-CN2'
CN3 = ROOT.parent / 'Tenkaichi3Decomp-WiiLocal-r5-CN3'
R5 = ROOT.parent / 'Tenkaichi3Decomp-WiiLocal-r5'
RUN = ROOT / 'CN3-Preview/Tenkaichi3Decomp'
OUT = ROOT / 'cn3-verification'
HISTORY = R5 / 'dist/Tenkaichi3Decomp-WiiLocal-r5/records/code-history'
SKIP = {'.git', 'build', 'dist', 'gamedata', '__pycache__'}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def snapshot(folder):
    files = {}
    for current, dirs, names in os.walk(folder):
        dirs[:] = sorted(d for d in dirs if d not in SKIP)
        for name in sorted(names):
            file = Path(current) / name
            files[file.relative_to(folder).as_posix()] = sha(file.read_bytes())
    return files


def normalized(data):
    return data.replace(b'\r\n', b'\n')


def online_tokens(source):
    text = source[source.index('static void quick_status('):source.index('void Ui_Toggle(')]
    text = text.replace('UiZh(Port_LobbyError())', 'Port_LobbyError()')
    pattern = re.compile(r'//[^\n]*|/\*.*?\*/|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'', re.S)
    text = pattern.sub(lambda m: '"text"' if m.group().startswith('"') else m.group() if m.group().startswith("'") else '', text)
    return re.sub(r'\s+', '', text)


def main():
    OUT.mkdir(exist_ok=True)
    before, after = snapshot(CN2), snapshot(CN3)
    captured = json.loads((ROOT / 'cn3-records/base-CN2-fixed-source-hashes.json').read_text('utf-8'))
    assert before == captured, 'CN2 base changed since the source snapshot'
    changed = sorted(n for n in before.keys() | after.keys() if before.get(n) != after.get(n))
    assert changed == ['local/CODE_CHANGES.md', 'local/build_cn3.py',
                       'port/src/gs/gs_draw.c', 'port/src/gs/menu_text.c'], changed
    source_hashes = {'before': before, 'after': after}
    (OUT / 'source-hashes.json').write_text(json.dumps(source_hashes, indent=2) + '\n', 'utf-8')

    def objects(folder):
        return {p.name: sha(p.read_bytes()) for p in sorted((folder / 'port/build/obj_win64').glob('*.o'))}
    old_objects, new_objects = objects(CN2), objects(CN3)
    assert len(old_objects) == len(new_objects) == 357
    changed_objects = sorted(n for n in old_objects.keys() | new_objects.keys()
                             if old_objects.get(n) != new_objects.get(n))
    assert changed_objects == ['gs_gs_draw.o', 'gs_menu_text.o'], changed_objects
    networking = {n: h for n, h in new_objects.items() if n.startswith('gs_net')}
    assert len(networking) == 5
    assert all(h == objects(R5)[n] for n, h in networking.items())
    (OUT / 'object-hashes.json').write_text(json.dumps({'CN2_fixed': old_objects, 'CN3': new_objects}, indent=2) + '\n', 'utf-8')

    with zipfile.ZipFile(HISTORY / 'official-0.1.38.1-source.zip') as archive:
        official = {n.split('/', 1)[1]: normalized(archive.read(n))
                    for n in archive.namelist() if not n.endswith('/')}
    prior_network = json.loads((R5 / 'port/build/network-invariants.json').read_text('utf-8'))
    protected = sorted(prior_network['sources'])
    assert len(protected) == 23
    exact_sources = {}
    for name in protected:
        current = normalized((CN3 / name).read_bytes())
        if name == 'src/battle/btl_seq.c':
            # CN2 translated the strings passed to font drawing calls. Prove that
            # removing only that display adapter recovers the whole official file.
            adapter = (b'#ifdef PORT\nextern const u16 *UiText_TranslateSpan(const u16 *original);\n'
                       b'#define BTLTEXT_STRING(s) ((u16 *)UiText_TranslateSpan(s))\n#else\n'
                       b'#define BTLTEXT_STRING(s) (s)\n#endif\n\n')
            assert current.count(adapter) == 1
            recovered = current.replace(adapter, b'')
            recovered = re.sub(rb'BTLTEXT_STRING\((p \+ [24]|str)\)', rb'\1', recovered)
            assert recovered == official[name], 'Battle sequencing differs beyond the prior text display adapter'
        else:
            assert current == official[name], name
            exact_sources[name] = sha(current)
    assert b'NET_VERSION = 5' in (CN3 / 'port/src/gs/net.c').read_bytes()
    assert online_tokens(official['port/src/gs/ui.cpp'].decode()) == online_tokens((CN3 / 'port/src/gs/ui.cpp').read_text('utf-8'))

    deployment = json.loads((OUT / 'deployment.json').read_text('utf-8'))
    for name, expected in deployment['program_files'].items():
        assert sha((RUN / name).read_bytes()) == expected, name
    for built, deployed in [('bt3.exe.mem', 'Tenkaichi3Decomp.exe.mem'), ('bt3.dat', 'Tenkaichi3Decomp.dat')]:
        assert (CN3 / 'port/build' / built).read_bytes() == (RUN / deployed).read_bytes()
    # Compare the executable after the same strip operation used for deployment.
    import tempfile
    with tempfile.TemporaryDirectory(prefix='bt3-cn3-exe-') as temp:
        output = Path(temp) / 'check.exe'
        subprocess.run([r'E:\BT3-Wii-tools\mingw64\bin\strip.exe', '--strip-all', '-o', str(output),
                        'port/build/bt3.exe'], cwd=CN3, check=True)
        def executable_content(data):
            # GNU strip stamps the PE header with the time of stripping and
            # updates its checksum. Compare all remaining bytes exactly.
            data = bytearray(data)
            pe = struct.unpack_from('<I', data, 0x3c)[0]
            assert data[pe:pe + 4] == b'PE\0\0'
            data[pe + 8:pe + 12] = bytes(4)
            data[pe + 24 + 64:pe + 24 + 68] = bytes(4)
            return data
        assert executable_content(output.read_bytes()) == executable_content((RUN / 'Tenkaichi3Decomp.exe').read_bytes())
    resource_files = {}
    for file in sorted((ROOT / 'cn3-resources').rglob('*')):
        if not file.is_file():
            continue
        rel = file.relative_to(ROOT / 'cn3-resources')
        if rel.parts[0] == 'fonts':
            target = RUN / rel
        elif rel.parts[0] in ('mods', 'game-text'):
            target = RUN / 'gamedata' / rel
        else:
            continue  # Build manifests and mapping provenance are records, not game assets.
        assert file.read_bytes() == target.read_bytes(), str(rel)
        resource_files[rel.as_posix()] = sha(file.read_bytes())
    base_run = ROOT / 'CN2-Preview/Tenkaichi3Decomp'
    assert (RUN / 'bt3_wii_controls.ini').read_bytes() == (base_run / 'bt3_wii_controls.ini').read_bytes()
    settings = dict(line.split('=', 1) for line in (RUN / 'bt3_settings.txt').read_text('utf-8').splitlines() if '=' in line)
    assert settings['menu_font_id'] == settings['text_font_id'] == '831785631'
    assert settings['menu_lang'] == '"zh-CN"' and settings['battle_font_id'] == '0'
    links = {}
    for name in ('disc', 'pzs3us0', 'pzs3us1', 'pzs3us2'):
        path = RUN / 'gamedata' / name
        assert path.lstat().st_reparse_tag == 0xA0000003  # Windows mount-point junction; Python 3.11 compatible.
        assert path.resolve() == (base_run / 'gamedata' / name).resolve()
        links[name] = str(path.resolve())

    # The native test emitted the complete row size and its placement in the
    # original cell. Check every translated menu cell for boundary clipping.
    rows = []
    for line in (OUT / 'menu-font/rendered.tsv').read_text('utf-8').splitlines():
        name, *values = line.split('\t')
        w, h, x, y, cw, ch = map(int, values)
        assert x >= 0 and y >= 0 and x + w <= cw and y + h <= ch, name
        rows.append(name)
    assert len(rows) == 314
    report = {'official_base': '11059a6d3e814cf36e6ca1f6307839f61c56f1cc',
              'runtime_source_deltas': changed, 'objects': 357, 'changed_objects': changed_objects,
              'unchanged_objects': 355, 'settings_repair_source_and_object_inherited_unchanged': True,
              'network_objects_byte_identical_to_fixed_CN2_and_r5': networking,
              'official_protected_sources_byte_identical_after_CRLF_normalization': exact_sources,
              'prior_CN2_battle_sequence_display_adapter_only': True,
              'online_UI_non_text_tokens_identical': True, 'protocol': 5,
              'deployment_program_verified': True,
              'executable_comparison_ignored_fields': ['GNU strip PE timestamp', 'PE checksum'],
              'deployed_resource_hashes': resource_files,
              'Wii_expression_file_unchanged': True, 'base_resource_junctions': links,
              'native_menu_rows_within_original_cells': len(rows), 'game_launched': False,
              'CN3_runtime_multiplayer_test': 'not performed'}
    (OUT / 'build-checks.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', 'utf-8')
    print('PASS: two renderer objects changed; 355 unchanged; five network objects identical; protocol 5.')
    print('PASS: deployed program/resources match; 314 native-rendered menu rows fit their cells.')


if __name__ == '__main__':
    main()
