"""Apply the user's approved 184 rounded-bold glyph identities, offline only.

Build a new immutable resource endpoint, test with the game's native renderer,
then back up and update the existing CN7 preview. No game source is edited.
"""
from collections import defaultdict
from pathlib import Path
import argparse
import hashlib
import json
import os
import shutil
import struct
import subprocess
import tempfile
import zipfile

from PIL import Image, ImageDraw, ImageFont
import build_cn2_adapter as pack
import build_cn3_resources as font_tools
import upstream_extract_eu_text as disc
import verify_cn6_resources as decode
import save_cn3_records as history
from prepare_cn7_source import source_files

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'cn7-resources'
REVIEW = ROOT / 'cn7-glyph-review-184-HD'
RES = ROOT / 'cn7-hd184-resources'
VERIFY = ROOT / 'cn7-hd184-verification'
RECORDS = ROOT / 'cn7-hd184-records'
GAME = ROOT / 'CN7-Preview/Tenkaichi3Decomp'
SOURCE = ROOT.parent / 'Tenkaichi3Decomp-WiiLocal-r8-CN7'
FONT = 'fonts/bt3cn-rounded-bold.ttf'
MOD = 'mods/pzs3us1/00004.bin'
APPROVAL = '我检查了你做的图片，字都是对的，不用再做校对表了'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read(path):
    return json.loads(path.read_text('utf-8'))


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', 'utf-8')


def files(folder):
    return {p.relative_to(folder).as_posix(): p.read_bytes()
            for p in sorted(folder.rglob('*')) if p.is_file()}


def hashes(data):
    return {n: sha(b) for n, b in data.items()}


def archive(path, data):
    if path.exists():
        # Resume incomplete recording only when the exact raw endpoint agrees.
        with zipfile.ZipFile(path) as z:
            assert z.testzip() is None and set(z.namelist()) == set(data), path
            assert all(z.read(n) == b for n, b in data.items()), path
        return
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for name, value in sorted(data.items()):
            z.writestr(name, value)
    with zipfile.ZipFile(path) as z:
        assert z.testzip() is None, path


def save_patch(name, before, after):
    """Reuse the established record algorithm, preserving raw line endings.

    No-index rename headers include the comparison folder in rename paths;
    disable rename detection so the patch applies directly to the raw ZIP.
    """
    with tempfile.TemporaryDirectory(prefix='bt3-cn7-hd184-record-') as temporary:
        directory = Path(temporary)
        for folder, endpoint in (('a', before), ('b', after), ('restored', before)):
            target = directory / folder
            target.mkdir()
            for relative, data in endpoint.items():
                path = target / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
        result = subprocess.run(['git', '-c', 'core.autocrlf=false', '-c', 'core.safecrlf=false',
            'diff', '--no-index', '--no-renames', '--no-ext-diff', '--full-index', '--binary',
            '--src-prefix=', '--dst-prefix=', '--', 'a', 'b'], cwd=directory, capture_output=True)
        assert result.returncode in (0, 1), result.stderr.decode(errors='replace')
        patch = RECORDS / name
        patch.write_bytes(result.stdout)
        for flags in (['--check'], ['--whitespace=nowarn']):
            run = subprocess.run(['git', '-c', 'core.autocrlf=false', 'apply', *flags, str(patch)],
                cwd=directory / 'restored', capture_output=True)
            assert run.returncode == 0, run.stderr.decode(errors='replace')
        assert files(directory / 'restored') == after
    return {'patch': name, 'sha256': sha(patch.read_bytes()),
        'base_files': len(before), 'target_files': len(after),
        'applied_and_all_raw_files_compared': True,
        'normalization': 'None; patch reconstructs exact raw ZIP endpoint bytes',
        'rename_detection': False}


def native_sheet(font, sheet, rgba, plane, output):
    run = subprocess.run([str(ROOT / 'tools/render_cn7_font.exe'), '--sheet',
        str(font.relative_to(ROOT)), str(sheet.relative_to(ROOT)),
        str(rgba.relative_to(ROOT)), str(plane), str(output.relative_to(ROOT))],
        capture_output=True, text=True, check=True)
    output.with_suffix('.tsv').write_text(run.stdout, 'utf-8')
    lines = run.stdout.splitlines()
    _, width, height = lines[0].split('\t')
    image = Image.frombytes('RGBA', (int(width), int(height)), output.read_bytes())
    result = {}
    for row in lines[1:]:
        code, x, y, w, h, top, bottom = row.split('\t')
        x, y, w, h, top, bottom = map(int, (x, y, w, h, top, bottom))
        assert (x + w)*4 <= image.width and (y + h)*4 <= image.height
        result[int(code, 16)] = (image.crop((x*4, y*4, (x+w)*4, (y+h)*4)), w, h, top, bottom)
    return result


def native_rows(font, baseline, output):
    output.mkdir()
    shutil.copy2(baseline / 'jobs.tsv', output / 'jobs.tsv')
    run = subprocess.run([str(ROOT / 'tools/render_cn7_font.exe'),
        str(font.relative_to(ROOT)), str((output / 'jobs.tsv').relative_to(ROOT)),
        str(output.relative_to(ROOT))], check=True, capture_output=True, text=True)
    (output / 'rendered.tsv').write_text(run.stdout, 'utf-8')
    assert run.stdout.splitlines() == (baseline / 'rendered.tsv').read_text('utf-8').splitlines()
    for name in baseline.glob('*.rgba'):
        assert name.read_bytes() == (output / name.name).read_bytes(), name
    return len(run.stdout.splitlines())


def build():
    assert not RES.exists() and not VERIFY.exists(), 'Preserve completed resource endpoints'
    VERIFY.mkdir()
    shutil.copytree(BASE, RES)
    approved = read(REVIEW / 'identification/manual-candidates.json')
    raw_codes = read(BASE / 'unreviewed-new-glyph-codes.json')
    old_ids = read(BASE / 'font-identities.json')
    assert len(approved) == 184 and set(approved) == set(raw_codes.values())
    assert not old_ids.keys() & approved.keys()
    shutil.copy2(REVIEW / 'preview-resources' / FONT, RES / FONT)
    old_tables, old_map = font_tools.cmap((BASE / FONT).read_bytes())
    data = (RES / FONT).read_bytes()
    tables, cmap = font_tools.cmap(data)
    wanted = {int(c, 16) for c in approved}
    assert set(cmap) - set(old_map) == wanted
    assert all(cmap[c] == gid for c, gid in old_map.items())
    assert all(cmap[int(c, 16)] == cmap[ord(ch)] for c, ch in approved.items())
    for tag, (at, size) in old_tables.items():
        if tag in (b'cmap', b'head'):
            continue
        offset, length = tables[tag]
        assert size == length and data[offset:offset+length] == (BASE / FONT).read_bytes()[at:at+size]
    write(RES / 'font-identities.json', old_ids | approved)
    normalized = read(BASE / 'normalized-cells.json')
    normalized.update(approved)
    write(RES / 'normalized-cells.json', normalized)
    (RES / 'unreviewed-new-glyph-codes.json').rename(RES / 'reviewed-new-glyph-codes.json')
    approval = {'date': '2026-10-26', 'user_message': APPROVAL,
        'approved_identities': approved, 'preview_font_sha256': sha(data),
        'preview_manifest_sha256': sha((REVIEW / 'records/manifest.json').read_bytes()),
        'new_review_page_requested': False}
    write(RES / 'cn7-hd184-user-approval.json', approval)

    before = disc.sections((BASE / MOD).read_bytes())
    parts = list(before)
    decode.OUT = VERIFY
    originals = decode.decode_original(parts[5], 5)
    table, count = struct.unpack_from('<II', parts[5], 20)
    old_rows = list(struct.iter_unpack('<HHH', parts[5][table:table+count*6]))
    assert wanted <= originals.keys() and count == 296
    face = ImageFont.truetype(str(RES / FONT), 18)
    planes = defaultdict(list)
    for code, u, v in old_rows:
        image = originals[code]
        if code in wanted:
            image = Image.new('RGBA', (20, 20), (128, 128, 128, 0))
            ImageDraw.Draw(image).text((1, 0), chr(code), font=face, fill=(128, 128, 128, 252))
        assert image.getchannel('A').getbbox(), f'{code:04X}'
        planes[(u >> 15) | ((v >> 15) << 1)].append((code, image))
    pack.OUT = VERIFY
    template, addresses = pack.font_template()
    assert set(planes) == {0, 1}
    parts[5] = pack.make_font(template, addresses,
        [((0, 68, 102, 126), planes[p]) for p in (0, 1)])
    (RES / MOD).write_bytes(pack.boot_archive(parts))
    after = disc.sections((RES / MOD).read_bytes())
    assert before[:5] == after[:5] and before[6:] == after[6:]
    new_cells = decode.decode_original(after[5], 5)
    assert new_cells.keys() == originals.keys()
    assert all(new_cells[c].tobytes() == originals[c].tobytes() for c in originals if c not in wanted)
    assert all(new_cells[c].size == (20, 20) for c in wanted)
    sheet = VERIFY / 'sheet-5.fnt'
    sheet.write_bytes(after[5])
    rendered = {}
    for plane in (0, 1):
        rgba = VERIFY / f'extra-5-{plane}.rgba'
        rendered.update(native_sheet(RES / FONT, sheet, rgba, plane, VERIFY / f'shared-5-{plane}.rgba'))
        # Warmup inputs must contain the exact new table and the unsubstituted atlas.
        tab, n = struct.unpack_from('<II', after[5], 20)
        header = struct.pack('<8I', 0x57335442, 1, 512, 512, n, 5, plane, 0)
        warm = header + after[5][tab:tab+n*6] + rgba.read_bytes()
        (RES / f'game-text/font-warmup/slot-5-plane-{plane}.bin').write_bytes(warm)
    assert rendered.keys() == originals.keys()
    preview = REVIEW / 'native-verification'
    reference_rows = (preview / 'shared-candidates.tsv').read_text('utf-8').splitlines()
    _, ref_w, ref_h = reference_rows[0].split('\t')
    reference = Image.frombytes('RGBA', (int(ref_w), int(ref_h)),
        (preview / 'shared-candidates.rgba').read_bytes())
    for row in reference_rows[1:]:
        code, x, y, w, h, top, bottom = row.split('\t')
        code = int(code, 16)
        x, y, w, h, top, bottom = map(int, (x, y, w, h, top, bottom))
        image, rw, rh, rt, rb = rendered[code]
        expected = reference.crop((x*4, y*4, (x+w)*4, (y+h)*4))
        assert (rw, rh, rt, rb) == (w, h, top, bottom) == (20, 20, 0, 0)
        assert image.tobytes() == expected.tobytes(), f'Approved preview mismatch {code:04X}'
        assert image.getchannel('A').getbbox()
    # The other member-5 glyphs retain their exact native output too.
    old_rendered = {}
    assert all(code in wanted for code, u, v in old_rows
               if ((u >> 15) | ((v >> 15) << 1)) == 1)
    # Old plane 1 has only raw ISO fallback glyphs and intentionally has no
    # TTF replacement output. All 112 preserved glyphs are on old plane 0.
    for plane in (0,):
        old_sheet = ROOT / 'cn7-verification/sheet-5.fnt'
        old_rendered.update(native_sheet(BASE / FONT, old_sheet,
            ROOT / f'cn7-verification/extra-5-{plane}.rgba', plane,
            VERIFY / f'old-shared-5-{plane}.rgba'))
    for code in originals.keys() - wanted:
        assert rendered[code][1:] == old_rendered[code][1:]
        assert rendered[code][0].tobytes() == old_rendered[code][0].tobytes(), f'{code:04X}'
    preserved = []
    for member, plane in ((2, 0), (2, 1), (3, 0), (3, 1), (4, 0)):
        output = VERIFY / f'shared-{member}-{plane}.rgba'
        native_sheet(RES / FONT, ROOT / f'cn7-verification/sheet-{member}.fnt',
            ROOT / f'cn7-verification/extra-{member}-{plane}.rgba', plane, output)
        assert output.read_bytes() == (ROOT / 'cn7-verification' / output.name).read_bytes()
        preserved.append(output.name)
    menu_count = native_rows(RES / FONT, ROOT / 'cn7-verification/accepted-menu', VERIFY / 'accepted-menu')
    art_count = native_rows(RES / FONT, ROOT / 'cn7-verification/new-art', VERIFY / 'new-art')
    assert menu_count == 320 and art_count == 74
    required = {ord(c) for r in read(RES / 'game-text/translations/ui/zh-CN.json')['labels'].values()
                for c in r['text'] if ord(c) >= 32 and ord(c) not in (0xfeff, 0xa0)}
    available = set(new_cells)
    for part in after[:5]:
        if part:
            at, n = struct.unpack_from('<II', part, 20)
            available.update(struct.unpack_from('<H', part, at+i*6)[0] for i in range(n))
    assert required <= available
    unchanged_warmups = []
    for path in (BASE / 'game-text/font-warmup').glob('slot-*.bin'):
        if not path.name.startswith('slot-5-'):
            assert path.read_bytes() == (RES / 'game-text/font-warmup' / path.name).read_bytes()
            unchanged_warmups.append(path.name)
    assert len(unchanged_warmups) == 9
    changed = [n for n, b in files(BASE).items() if (RES / n).is_file() and (RES / n).read_bytes() != b]
    assert set(changed) == {FONT, MOD, 'font-identities.json', 'normalized-cells.json',
        'game-text/font-warmup/slot-5-plane-0.bin', 'game-text/font-warmup/slot-5-plane-1.bin'}
    checks = {'edition': 'CN7-HD184', 'user_confirmed_glyphs': 184,
        'native_new_glyphs_identical_to_approved_previews': 184,
        'missing_or_fallback_new_glyphs': 0, 'new_glyph_cell_advance_height': 20,
        'unchanged_member5_glyph_native_outputs': len(originals) - 184,
        'old_font_mappings_outlines_metrics_unchanged': True,
        'old_font_member_native_atlases_identical': preserved,
        'accepted_menu_outputs_identical': menu_count, 'CN7_artwork_outputs_identical': art_count,
        'catalog_required_glyphs': len(required), 'missing_catalog_glyphs': 0,
        'old_warmup_inputs_byte_identical': len(unchanged_warmups), 'updated_warmup_inputs': 2,
        'translated_text_catalogs_changed': False, 'runtime_source_changed': False,
        'program_files_changed': False, 'protocol': 5, 'game_launched': False,
        'in_game_visual_test': 'pending user test', 'changed_existing_resource_files': changed}
    write(VERIFY / 'checks.json', checks)
    write(RES / 'cn7-hd184-manifest.json', checks)
    print('PASS: 184 approved native glyphs; 112 other cells, five old atlases, 320 menu and 74 artwork outputs unchanged', flush=True)


def deployment_files():
    return {FONT: FONT, MOD: 'gamedata/' + MOD,
        'game-text/font-warmup/slot-5-plane-0.bin': 'gamedata/game-text/font-warmup/slot-5-plane-0.bin',
        'game-text/font-warmup/slot-5-plane-1.bin': 'gamedata/game-text/font-warmup/slot-5-plane-1.bin'}


def personal_hashes():
    paths = [GAME / 'bt3_settings.txt', GAME / 'bt3_wii_controls.ini']
    paths += [p for folder in ('saves', 'wii_profiles') for p in (GAME / folder).rglob('*') if p.is_file()]
    return {p.relative_to(GAME).as_posix(): sha(p.read_bytes()) for p in paths if p.is_file()}


def deploy():
    assert read(VERIFY / 'checks.json')['native_new_glyphs_identical_to_approved_previews'] == 184
    assert not (VERIFY / 'deployment.json').exists(), 'Preserve completed deployments'
    RECORDS.mkdir(exist_ok=True)
    programs = read(ROOT / 'cn7-verification/deployment.json')['program_files']
    assert all(sha((GAME / n).read_bytes()) == h for n, h in programs.items())
    source = hashes(source_files(SOURCE))
    assert source == read(ROOT / 'cn7-records/source-endpoint-hashes.json')['CN7']
    personal = personal_hashes()
    planned = deployment_files()
    backup = {dest: (GAME / dest).read_bytes() for dest in planned.values()}
    for origin, dest in planned.items():
        assert backup[dest] == (BASE / origin).read_bytes(), f'Preview modified since CN7 build: {dest}'
    readme = 'CN7-使用说明.txt'
    backup[readme] = (GAME / readme).read_bytes()
    text = backup[readme].decode('utf-8-sig')
    old = '184个新出现、尚未核对字义的字暂用汉化ISO原字形；请用上一级目录中的184字核对表填写，之后统一生成高清字。'
    assert old in text
    archive(RECORDS / 'CN7-preview-before-HD184.zip', backup)
    for origin, dest in planned.items():
        shutil.copy2(RES / origin, GAME / dest)
        assert (GAME / dest).read_bytes() == (RES / origin).read_bytes()
    text = text.replace(old, '2026-10-26：新增184个字已由用户确认，全部换成寒蝉圆黑体·粗体，统一20×20字格、字号和基线。无需再填写校对表。')
    (GAME / readme).write_text(text, 'utf-8-sig')
    assert personal_hashes() == personal
    assert all(sha((GAME / n).read_bytes()) == h for n, h in programs.items())
    assert hashes(source_files(SOURCE)) == source
    report = {'edition': 'CN7-HD184', 'date': '2026-10-26', 'game': str(GAME),
        'updated_resource_files': {dest: sha((GAME / dest).read_bytes()) for dest in planned.values()},
        'programs_unchanged': programs, 'runtime_source_unchanged_files': len(source),
        'settings_saves_profiles_unchanged': personal, 'backup': str(RECORDS / 'CN7-preview-before-HD184.zip'),
        'runtime_network_protocol_changed': False, 'protocol': 5, 'game_launched': False,
        'installed_E_game_modified': False, 'Git_commit_push_PR': False}
    write(VERIFY / 'deployment.json', report)
    write(GAME / 'CN7-HD184-Build.json', report)
    update = {'Tenkaichi3Decomp/' + dest: (GAME / dest).read_bytes() for dest in planned.values()}
    for name in (readme, 'CN7-HD184-Build.json'):
        update['Tenkaichi3Decomp/' + name] = (GAME / name).read_bytes()
    archive(ROOT / 'CN7-HD184-resource-update.zip', update)
    print('Updated existing CN7 preview resources; programs, source, settings and saves verified unchanged', flush=True)


def records():
    assert not (RECORDS / 'manifest.json').exists(), 'Preserve completed records'
    assert read(VERIFY / 'deployment.json')['edition'] == 'CN7-HD184'
    history.OUT = RECORDS
    before, after = files(BASE), files(RES)
    archive(RECORDS / 'CN7-complete-resources-before.zip', before)
    archive(RECORDS / 'CN7-HD184-complete-resources.zip', after)
    patches = [save_patch('CN7-to-HD184-resources.patch', before, after)]
    write(RECORDS / 'resource-endpoint-hashes.json', {'CN7': hashes(before), 'CN7-HD184': hashes(after)})
    with zipfile.ZipFile(ROOT / 'cn7-records/CN7-analysis-and-verification-tools.zip') as z:
        old_tools = {n: z.read(n) for n in z.namelist() if not n.endswith('/')}
    new_tools = dict(old_tools)
    added_tools = ['prepare_cn7_newglyph_ocr.py', 'identify_cn7_newglyphs.py',
                   'build_cn7_newglyph_hd.py', 'apply_cn7_hd184.py']
    for name in added_tools:
        new_tools['tools/' + name] = (ROOT / 'tools' / name).read_bytes()
    archive(RECORDS / 'CN7-tools-before.zip', old_tools)
    archive(RECORDS / 'CN7-HD184-tools-after.zip', new_tools)
    patches.append(save_patch('CN7-to-HD184-tools.patch', old_tools, new_tools))
    write(RECORDS / 'tool-endpoint-hashes.json', {'CN7': hashes(old_tools), 'CN7-HD184': hashes(new_tools)})
    evidence = {}
    for folder in ('identification', '对照图', 'native-verification', 'preview-resources', 'records'):
        evidence.update({folder + '/' + n: b for n, b in files(REVIEW / folder).items()})
    archive(RECORDS / 'approved-glyph-identification-and-images.zip', evidence)
    # Native raw output and jobs are retained; intermediate decoder maps are reproducible.
    archive(RECORDS / 'native-verification.zip', files(VERIFY))
    for name in ('checks.json', 'deployment.json'):
        shutil.copy2(VERIFY / name, RECORDS / name)
    for name in ('source-endpoint-hashes.json', 'network-checks.json', 'build-checks.json'):
        shutil.copy2(ROOT / 'cn7-records' / name, RECORDS / ('CN7-unchanged-' + name))
    archive(RECORDS / 'CN7-unchanged-complete-source.zip', source_files(SOURCE))
    shutil.copy2(RES / 'cn7-hd184-user-approval.json', RECORDS / 'user-approval.json')
    font_source = RECORDS / 'font-source'
    font_source.mkdir()
    for name in ('ChillRoundGothic_Bold.ttf', 'ChillRoundGothic-OFL.txt'):
        shutil.copy2(ROOT / 'cn3-font-options/vendor' / name, font_source / name)
    shutil.copy2(ROOT / 'CN7-HD184-resource-update.zip', RECORDS / 'CN7-HD184-resource-update.zip')
    (RECORDS / 'README.md').write_text('''# CN7-HD184 local font update — 2026-10-26

The user checked the generated images and explicitly confirmed all 184 identities. Their original message and complete code-to-character map are in user-approval.json. No further review page was made or requested.

The game runtime source and matched EXE/mem/dat/SDL files are unchanged. This edition adds exactly 184 cmap aliases to the existing rounded bold TTF; all prior aliases, outlines and metrics stay identical. Member 5 of the boot font archive now uses normalized 20×20 cells for these 184 codes. The two exact member-5 warmup inputs are regenerated. The other 112 member-5 glyphs, first five boot members, nine existing warmup inputs, 320 accepted menu renders and 74 CN7 artwork renders pass exact comparisons. Every new native glyph matches the image the user approved; none is missing or a fallback. Text catalogs and game scripts stay unchanged.

CN7-to-HD184-resources.patch contains the actual binary-capable resource delta. CN7-to-HD184-tools.patch preserves all new identification, preview and finalization tool code. Both patches were applied in clean temporary directories and every reconstructed target file compared against raw ZIP bytes, including original line endings. Rename detection is disabled to keep no-index paths directly applicable. Full raw before/after ZIPs and SHA-256 manifests are retained, including renamed reviewed-new-glyph-codes.json and updated font-identities/normalized-cells metadata. Historical CN7 resources, records and review evidence are untouched. The historical preview evidence still says candidate; user-approval.json is the later confirmation.

The existing CN7-Preview/Tenkaichi3Decomp was updated in place after backing up the four replaced resources and readme in CN7-preview-before-HD184.zip. Programs and all current settings, saves and Wii profiles are byte-verified unchanged. CN7-HD184-resource-update.zip is an overlay for CN7 only, with no programs, personal files or base-disc installation. To revert, restore the backup into the game directory and remove only the new CN7-HD184-Build.json marker. Other installed game directories were not modified.

To reproduce from the CN7 resource endpoint, restore the tools-after ZIP at the analysis root, retain the original private font inputs and native test fixtures from the preceding CN7 records, restore the approved image evidence to cn7-glyph-review-184-HD, and run apply_cn7_hd184.py build. The direct resource patch is self-contained and does not need OCR or the review webpage. Complete unchanged runtime source is retained for future upstream merging; inherit the prior CN7 source delta and add this resource delta separately. Keep exact endpoints rather than overwriting later official/generated assets blindly.

Verification was offline and used the actual native font renderer. No game was launched and no game input, foreground manipulation or desktop screenshot was used. In-game positioning still awaits user testing. Networking and protocol code were not edited; protocol remains 5. No Git commit, remote update or PR change was made. Font source and OFL license are included. ISO-derived inputs are private local materials.
''', 'utf-8')
    manifest = {'edition': 'CN7-HD184', 'date': '2026-10-26', 'approval': APPROVAL,
        'reviewed_new_identities': 184, 'patches': patches, 'new_tool_sources': added_tools,
        'runtime_source_modified': False, 'program_modified': False, 'protocol': 5,
        'game': str(GAME), 'game_launched': False, 'Git_commit_push_PR': False}
    write(RECORDS / 'manifest.json', manifest)
    write(RECORDS / 'record-file-hashes.json', hashes(files(RECORDS)))
    bundle = ROOT / 'CN7-HD184-code-resources-and-records.zip'
    archive(bundle, {'cn7-hd184-records/' + n: b for n, b in files(RECORDS).items()})
    write(ROOT / 'CN7-HD184-records-archive.json', {'path': str(bundle),
        'sha256': sha(bundle.read_bytes()), 'bytes': bundle.stat().st_size, 'ZIP_integrity': 'passed'})
    print('Saved and reconstructed resource/tool patches, complete endpoints, approval and native verification', flush=True)
    print('Records:', RECORDS, flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage', choices=('build', 'deploy', 'records'))
    args = parser.parse_args()
    os.chdir(ROOT)
    {'build': build, 'deploy': deploy, 'records': records}[args.stage]()
