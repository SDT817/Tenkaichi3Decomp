"""Build the two narrowly changed action sources; preserve all other r20 objects."""
import contextlib
import hashlib
import io
import json
import build_windows as b

base = b.ROOT.parent / 'Tenkaichi3Decomp-WiiLocal-r20-Lobby016'
def hashes(path):
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in path.glob('*.o')}

before = hashes(base / 'port/build/obj_win64')
logs = []
for name in ('btl_act_d.c', 'btl_char_action.c'):
    result = b.cc(b.ROOT / 'src/battle' / name)
    logs.append(name + '\n' + result[2])
    assert result[0] is not None, result[2]
(b.ROOT / 'port/build/trunks-compile.log').write_text('\n'.join(logs), 'utf-8')
after = hashes(b.undefined.OBJ)
changed = sorted(n for n in before if before[n] != after[n])
assert changed == ['battle_btl_act_d.o', 'battle_btl_char_action.o'], changed
assert hashes(base / 'port/build/obj_data_win64') == hashes(b.ROOT / 'port/build/obj_data_win64')
output = io.StringIO()
with contextlib.redirect_stdout(output):
    import link
log = output.getvalue()
(b.ROOT / 'port/build/trunks-link.log').write_text(log, 'utf-8')
assert 'link OK' in log, log
(b.ROOT / 'port/build/trunks-objects.json').write_text(json.dumps({
    'changed_objects': changed, 'before': before, 'after': after,
}, indent=2) + '\n', 'utf-8')
print(log, flush=True)
