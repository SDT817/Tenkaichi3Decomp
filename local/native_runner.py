"""Run a saved check with compiler paths relative to the source checkout."""
from pathlib import Path
import runpy
import sys
from native_paths import install, ROOT

install()
script = ROOT / sys.argv[1]
sys.argv = [str(script), *sys.argv[2:]]
sys.path.insert(0, str(script.parent))
if script.name == 'make_state.py':
    namespace = runpy.run_path(str(script), run_name='bt3_local_state')
    original = namespace['is_game']
    def is_game(obj):
        path = Path(obj)
        return original(str(path if path.is_absolute() else ROOT / path))
    namespace['main'].__globals__['is_game'] = is_game
    namespace['main']()
    spans = Path(str(namespace['EXE']) + '.mem').read_text().splitlines()
    assert len(spans) > 2, 'Game-state ranges must not be empty'
else:
    runpy.run_path(str(script), run_name='__main__')
