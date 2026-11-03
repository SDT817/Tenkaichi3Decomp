"""Three-way source merge from the exact old/new official ZIPs, without Git writes."""
from pathlib import Path
import json,os,shutil,subprocess,tempfile,zipfile,hashlib

ROOT=Path(__file__).resolve().parents[1]
OLD=ROOT.parent/'Tenkaichi3Decomp-WiiLocal-r5-CN4'
NEW=ROOT.parent/'Tenkaichi3Decomp-WiiLocal-r6-CN5'
UP=ROOT/'cn5-upstream'
RECORDS=ROOT/'cn5-records'
OLDZIP=ROOT/'cn4-records/official-0.1.38.1-source.zip'
SKIP={'.git','build','dist','gamedata','__pycache__'}


def norm(data):
    if data is None:return None
    if b'\0' not in data:
        try:data.decode('utf-8');return data.replace(b'\r\n',b'\n')
        except UnicodeDecodeError:pass
    return data


def zipfiles(path):
    with zipfile.ZipFile(path) as z:
        return {n.split('/',1)[1]:norm(z.read(n)) for n in z.namelist() if not n.endswith('/')}


def files(folder):
    result={}
    for cur,dirs,names in os.walk(folder):
        dirs[:]=sorted(d for d in dirs if d not in SKIP)
        for name in sorted(names):
            p=Path(cur)/name;result[p.relative_to(folder).as_posix()]=p.read_bytes()
    return result


def write_json(path,data):
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n','utf-8')


def main():
    assert not NEW.exists(),'Preserve existing source trees'
    manifest=json.loads((UP/'manifest.json').read_text('utf-8')) if (UP/'manifest.json').exists() else {
        'source_archive':'official-v0.1.38.3-source.zip','commit':'13ecf4f3eaf4ba5b285adba33f81f699246598a9','tag':'v0.1.38.3'}
    ancestor,official=zipfiles(OLDZIP),zipfiles(UP/manifest['source_archive'])
    local_raw=files(OLD);local={n:norm(d) for n,d in local_raw.items()}
    RECORDS.mkdir(exist_ok=True)
    write_json(RECORDS/'base-CN4-source-hashes.json',{n:hashlib.sha256(d).hexdigest() for n,d in local_raw.items()})
    NEW.mkdir()
    for name,data in official.items():
        target=NEW/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
    results={};conflicts=[]
    for name in sorted(ancestor.keys()|local.keys()):
        a,l,u=ancestor.get(name),local.get(name),official.get(name)
        if l==a:continue
        target=NEW/name
        if a is None:
            assert u is None or u==l,'Concurrent additions: '+name
            merged=l;status='local addition'
        elif l is None:
            assert u==a,'Delete/modify conflict: '+name
            target.unlink();results[name]='local deletion';continue
        elif u==a:
            merged=l;status='local modification; upstream unchanged'
        elif l==u:
            merged=u;status='same change upstream and local'
        else:
            assert u is not None and b'\0' not in a+l+u,'Binary/delete conflict: '+name
            with tempfile.TemporaryDirectory(prefix='bt3-cn5-threeway-') as temp:
                paths=[Path(temp)/p for p in ('local','ancestor','official')]
                for path,data in zip(paths,(l,a,u)):path.write_bytes(data)
                result=subprocess.run(['git','merge-file','-p','-L','CN4','-L','official-0.1.38.1',
                       '-L','official-0.1.38.3',*map(str,paths)],capture_output=True)
                assert 0<=result.returncode<=127,result.stderr
                merged=result.stdout;status=f'three-way merge: {result.returncode} conflicts'
                if result.returncode:conflicts.append(name)
        target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(merged);results[name]=status
    # Retain the old intermediate files, then build invalidation handles source/header changes.
    shutil.copytree(OLD/'port/build',NEW/'port/build',ignore=shutil.ignore_patterns('__pycache__'))
    changed=[n for n in sorted(ancestor.keys()|official.keys()) if ancestor.get(n)!=official.get(n)]
    report={'from_official':'11059a6d3e814cf36e6ca1f6307839f61c56f1cc','to_official':manifest['commit'],
            'release':manifest['tag'],'official_changes':changed,'local_changes':results,
            'conflicted_files':conflicts,'unresolved_conflicts':bool(conflicts)}
    write_json(RECORDS/'three-way-merge.json',report)
    print('Official source changes:',len(changed));print('\n'.join(changed))
    print('Local source changes carried forward:',len(results))
    print('Conflicts:',conflicts)


if __name__=='__main__':main()
