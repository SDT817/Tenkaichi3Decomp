"""Copy verified, newly named r5 artifacts to the user's existing release folder."""
from pathlib import Path
import hashlib
import shutil

ROOT = Path(__file__).resolve().parents[1]
NAME = 'Tenkaichi3Decomp-WiiLocal-r5'
source = ROOT / 'dist' / NAME
target = Path(r'E:\PS2 yizhi\ab')
files = sorted(source.glob(NAME + '-*.zip'))
assert len(files) == 4
assert not (target / NAME).exists()
for file in files:
    assert not (target / file.name).exists()
    expected = (source / (file.name + '.sha256')).read_text().split()[0]
    assert hashlib.sha256(file.read_bytes()).hexdigest() == expected
    shutil.copy2(file, target / file.name)
    shutil.copy2(source / (file.name + '.sha256'), target / (file.name + '.sha256'))
    assert hashlib.sha256((target / file.name).read_bytes()).hexdigest() == expected
    print(target / file.name, file.stat().st_size, flush=True)
shutil.copytree(source / NAME / 'Tenkaichi3Decomp', target / NAME / 'Tenkaichi3Decomp')
print('Verified identical public copies; old editions were not overwritten.')
