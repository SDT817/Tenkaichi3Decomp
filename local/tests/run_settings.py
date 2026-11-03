"""Reproduce full-table data loss and verify persistence in fresh processes.

All writes use temporary copies; installed games and personal settings are read
only. --expect-bug checks that the unpatched 256-entry implementation fails in
the observed way, rather than silently accepting a passing regression test.
"""
from pathlib import Path
import argparse
import hashlib
import json
import os
import re
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[2]
ANALYSIS = ROOT.parent / 'Chinese-local-analysis-20261022'
PREVIEW = ANALYSIS / 'CN2-Preview/Tenkaichi3Decomp'
RECORDS = ROOT / 'port/build/cn6-test-records'
OUT = ROOT / 'port/build/local-tests'
EXPECTED = {'language_loaded': 1, 'skip_logos': 1, 'skip_intro': 1,
            'menus_43': 1, 'ui_scale': 125}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--expect-bug', action='store_true')
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    RECORDS.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env['PATH'] = r'E:\BT3-Wii-tools\mingw64\bin;' + env['PATH']
    compiler = r'E:\BT3-Wii-tools\mingw64\bin\gcc.exe'
    exe = OUT / ('settings-before.exe' if args.expect_bug else 'settings-fixed.exe')
    subprocess.run([compiler, '-O2', '-Wall', '-Wextra', 'local/tests/test_settings.c',
                    'port/src/plat_settings.c', '-lwinpthread', '-o', str(exe.relative_to(ROOT))],
                   cwd=ROOT, env=env, check=True)
    report = {'expected_bug': args.expect_bug, 'game_launched': False, 'cases': {}}
    frozen = ANALYSIS / 'settings-save-fix-20261022/before/Chinese-local-analysis-20261022/CN2-Preview/Tenkaichi3Decomp/bt3_settings.txt'
    fixtures = {'current_installed': Path(r'D:\Tenkaichi3Decomp\bt3_settings.txt'),
                'preview_256': frozen if frozen.is_file() else PREVIEW / 'bt3_settings.txt'}
    for title, fixture in fixtures.items():
        if not fixture.is_file():
            continue
        original = fixture.read_bytes()
        before = dict(re.findall(r'^([a-z0-9_]+)=(-?\d+)\r?$', original.decode('utf-8-sig'), re.M))
        assert len(before) >= 176, 'The real settings fixture was not parsed'
        with tempfile.TemporaryDirectory(prefix='bt3-settings-') as temp:
            file = Path(temp) / 'settings.txt'
            file.write_bytes(original)
            env['BT3_SETTINGS'] = str(file)
            run = lambda action: subprocess.run([str(exe), action], cwd=ROOT, env=env,
                                                 capture_output=True, text=True)
            initial = run('inspect')
            assert initial.returncode == 0, initial.stderr
            assert run('save').returncode == 0
            result = run('inspect')
            assert result.returncode == 0, result.stderr
            loaded = json.loads(result.stdout)
            after = dict(re.findall(r'^([a-z0-9_]+)=(-?\d+)$', file.read_text('utf-8'), re.M))
            preserved = all(after.get(key) == value for key, value in before.items() if key not in EXPECTED)
            assert preserved
            passed = loaded == EXPECTED
            expected = not (args.expect_bug and title == 'preview_256')
            assert passed == expected, (title, loaded)
            assert fixture.read_bytes() == original, 'Personal fixture was modified'
            report['cases'][title] = {'input_numeric_entries': len(before),
                                     'initial': json.loads(initial.stdout), 'after_restart': loaded,
                                     'existing_values_preserved': preserved, 'menu_persisted': passed,
                                     'fixture_sha256': hashlib.sha256(original).hexdigest()}
    with tempfile.TemporaryDirectory(prefix='bt3-settings-many-') as temp:
        file = Path(temp) / 'settings.txt'
        env['BT3_SETTINGS'] = str(file)
        subprocess.run([str(exe), 'fill'], cwd=ROOT, env=env, check=True)
        result = subprocess.run([str(exe), 'verify'], cwd=ROOT, env=env, capture_output=True, text=True)
        assert (result.returncode == 0) != args.expect_bug, result.stdout + result.stderr
        report['cases']['5000_numbers_64_texts_and_trailing_language'] = {
            'persisted': result.returncode == 0, 'output': (result.stdout + result.stderr).strip()}
    filename = 'baseline-reproduction.json' if args.expect_bug else 'persistence-tests.json'
    (RECORDS / filename).write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
