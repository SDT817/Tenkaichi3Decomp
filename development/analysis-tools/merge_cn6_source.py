"""Merge the accepted local CN5 source onto exact official v0.1.38.7; no Git writes."""
from pathlib import Path
import difflib, hashlib, json, shutil, subprocess, tempfile
from merge_cn5_source import zipfiles, files, norm

ROOT = Path(__file__).resolve().parents[1]
OLD = ROOT.parent / 'Tenkaichi3Decomp-WiiLocal-r6-CN5'
NEW = ROOT.parent / 'Tenkaichi3Decomp-WiiLocal-r7-CN6'
UP = ROOT / 'cn6-upstream-20261025'
OUT = ROOT / 'cn6-records'
OLDZIP = ROOT / 'cn5-upstream/official-v0.1.38.3-source.zip'

def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', 'utf-8')

def main():
    assert not NEW.exists(), 'Preserve existing source trees'
    manifest = json.loads((UP/'manifest.json').read_text('utf-8'))
    ancestor, official = zipfiles(OLDZIP), zipfiles(UP/manifest['source_archive'])
    raw = files(OLD)
    local = {n: norm(b) for n,b in raw.items()}
    OUT.mkdir(exist_ok=True)
    write_json(OUT/'base-CN5-source-hashes.json', {n:hashlib.sha256(b).hexdigest() for n,b in raw.items()})
    NEW.mkdir()
    for folder in (NEW, UP/'official-source'):
        folder.mkdir(exist_ok=True)
        for name, data in official.items():
            p=folder/name; p.parent.mkdir(parents=True,exist_ok=True); p.write_bytes(data)
    results={}; conflicts=[]
    for name in sorted(ancestor.keys() | local.keys()):
        a,l,u = ancestor.get(name), local.get(name), official.get(name)
        if l==a: continue
        target=NEW/name
        if a is None:
            assert u is None or u==l, 'Concurrent addition: '+name
            merged=l; status='local addition'
        elif l is None:
            assert u==a, 'Delete/modify conflict: '+name
            target.unlink(); results[name]='local deletion'; continue
        elif u==a:
            merged=l; status='local modification; upstream unchanged'
        elif l==u:
            merged=u; status='same upstream and local change'
        else:
            assert u is not None and b'\0' not in a+l+u, 'Binary/delete conflict: '+name
            with tempfile.TemporaryDirectory(prefix='bt3-cn6-merge-') as temp:
                paths=[Path(temp)/p for p in ('local','ancestor','official')]
                for p,b in zip(paths,(l,a,u)): p.write_bytes(b)
                result=subprocess.run(['git','merge-file','-p','-L','CN5','-L','official-v0.1.38.3',
                                       '-L',manifest['tag'],*map(str,paths)],capture_output=True)
                assert 0<=result.returncode<=127, result.stderr
                merged=result.stdout; status=f'three-way merge: {result.returncode} conflicts'
                if result.returncode: conflicts.append(name)
        target.parent.mkdir(parents=True,exist_ok=True); target.write_bytes(merged); results[name]=status
    shutil.copytree(OLD/'port/build', NEW/'port/build', ignore=shutil.ignore_patterns('__pycache__'))
    changed=[n for n in sorted(ancestor.keys()|official.keys()) if ancestor.get(n)!=official.get(n)]
    diffs=[]
    for n in changed:
        diffs += list(difflib.unified_diff(ancestor.get(n,b'').decode('utf-8').splitlines(True),
                      official.get(n,b'').decode('utf-8').splitlines(True),fromfile='v0.1.38.3/'+n,tofile=manifest['tag']+'/'+n))
    (OUT/'upstream-changes.diff').write_text(''.join(diffs),'utf-8')
    write_json(OUT/'three-way-merge.json', {'from_official':manifest['official_base_before'],
                'to_official':manifest['commit'],'release':manifest['tag'], 'official_changes':changed,
                'local_changes':results, 'conflicted_files':conflicts, 'unresolved_conflicts':bool(conflicts)})
    print('Official changed files:',len(changed))
    print('Carried local files:',len(results))
    print('Conflicts:',conflicts)

if __name__=='__main__':main()
