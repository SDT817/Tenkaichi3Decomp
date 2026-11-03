"""Windows compiler adapter for a checkout in a non-ASCII directory."""
from pathlib import Path
import os
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
_run = subprocess.run

def relative(value):
    value = str(value)
    return value.replace(str(ROOT).replace('\\', '/') + '/', '').replace(str(ROOT) + '\\', '')

def run(command, **kwargs):
    if isinstance(command, (list, tuple)) and Path(kwargs.get('cwd', os.getcwd())).resolve() == ROOT:
        command = [relative(a) for a in command]
        if len(command) > 1 and command[0] == sys.executable and command[1].replace('\\', '/').startswith('port/tools/'):
            command = [command[0], 'local/native_runner.py', *command[1:]]
        for arg in command:
            if arg.startswith('@'):
                rsp = ROOT / arg[1:]
                if rsp.is_file():
                    text = rsp.read_text(encoding='utf-8')
                    if rsp.name == 'link.rsp':
                        library = str(Path(os.environ.get('BT3_LOCAL_TOOLS', r'E:\BT3-Wii-tools')) / 'mingw64/lib/libz.a').replace('\\', '/')
                        text += '\n"' + library + '"\n'  # Offline profile compression, statically linked.
                    rsp.write_text(relative(text), encoding='utf-8')
    if kwargs.get('text') or kwargs.get('universal_newlines'):
        kwargs.setdefault('errors', 'replace')
    return _run(command, **kwargs)

def install():
    subprocess.run = run
