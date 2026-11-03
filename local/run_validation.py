"""Run the retained control checks and record their actual output."""
from pathlib import Path
import json
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
out = root / 'port/build/r5-tests.json'
report = json.loads(out.read_text(encoding='utf-8')) if out.exists() else {}
for name in ('run_bindings', 'run_battle', 'run_parser_parity', 'run_profiles', 'run_editor', 'run_navigation', 'check_network'):
    if name in report and report[name]['exit_code'] == 0:
        print(name, 'already passed in this unchanged build', flush=True)
        continue
    result = subprocess.run([sys.executable, 'local/native_runner.py', f'local/tests/{name}.py'], cwd=root, capture_output=True, text=True, encoding='utf-8', errors='replace')
    report[name] = {'exit_code': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr}
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(name, result.returncode, result.stdout, result.stderr, flush=True)
    if result.returncode: sys.exit(result.returncode)
