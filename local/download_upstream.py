from pathlib import Path
import hashlib
import urllib.request
import zipfile

out = Path(__file__).resolve().parents[1] / 'port/build/upstream-0.1.38.1-windows-x64.zip'
url = 'https://github.com/z3xox/Tenkaichi3Decomp/releases/download/v0.1.38.1/Tenkaichi3Decomp-windows-x64.zip'
with urllib.request.urlopen(url, timeout=60) as source:
    data = source.read()
out.write_bytes(data)
with zipfile.ZipFile(out) as archive:
    assert archive.testzip() is None
print(out, len(data), hashlib.sha256(data).hexdigest())
