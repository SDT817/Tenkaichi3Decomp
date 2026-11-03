"""Check the unchanged r22 source imported for the 0.17 collaboration release."""
from pathlib import Path
import hashlib
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / 'development/provenance/source-sha256.json'
PUBLICATION_METADATA = {'.gitignore', 'README.md'}


def main():
    expected = json.loads(MANIFEST.read_text('utf-8'))
    failures = []
    for name, digest in expected.items():
        path = ROOT / name
        if not path.is_file():
            failures.append((name, 'missing'))
        elif name not in PUBLICATION_METADATA and hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            failures.append((name, 'modified'))
    if failures:
        for name, reason in failures:
            print(f'{reason}: {name}')
        print(f'FAIL: {len(failures)} recorded files differ from accepted r22.')
        return 1
    print(f'PASS: {len(expected)} recorded r22 files checked; runtime, tests and build source unchanged.')
    print('Only root README/ignore metadata may differ for source publication.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
