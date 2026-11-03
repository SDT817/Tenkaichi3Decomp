"""Make a clean QA runtime from the matching official release and this build."""
from pathlib import Path
import shutil
import subprocess
import zipfile
from native_paths import install, ROOT

install()
out = ROOT / 'port/build/qa-local/Tenkaichi3Decomp'
out.mkdir(parents=True, exist_ok=True)
with zipfile.ZipFile(ROOT / 'port/build/upstream-0.1.38.9-windows-x64.zip') as archive:
    names = [item.filename for item in archive.infolist() if not item.is_dir()]
    for item in archive.infolist():
        p = Path(item.filename)
        assert p.parts[0] == 'Tenkaichi3Decomp' and '..' not in p.parts
        if not item.is_dir():
            target = out / Path(*p.parts[1:])
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.read(item))
for source, target in [('bt3.exe', 'Tenkaichi3Decomp.exe'), ('bt3.exe.mem', 'Tenkaichi3Decomp.exe.mem'), ('bt3.dat', 'Tenkaichi3Decomp.dat')]:
    shutil.copy2(ROOT / 'port/build' / source, out / target)
subprocess.run([r'E:\BT3-Wii-tools\mingw64\bin\strip.exe', '--strip-all', str(out / 'Tenkaichi3Decomp.exe')], cwd=ROOT, check=True)
assert len((out / 'Tenkaichi3Decomp.exe.mem').read_text().splitlines()) > 2
with zipfile.ZipFile(ROOT / 'port/build/r11-qa.zip', 'w', zipfile.ZIP_DEFLATED) as archive:
    for name in sorted(names):
        archive.write(out / Path(*Path(name).parts[1:]), name)
print('Prepared stripped r11 QA runtime and archive')
