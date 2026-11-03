"""Verify a public signed release, then copy assets first and latest.json last."""
import argparse
from contextlib import closing
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import sqlite3

PUBLIC='ce5990d7da701b89b1deb00d15a8adbfe1a09b52cb7bd57b1f36f84abae11de4'
ASSET='Tenkaichi3Decomp-windows-x64.zip'

def install(release,target=None):
    spec=importlib.util.spec_from_file_location('update_key',Path(__file__).parent/'port/tools/update_key.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    manifest=json.loads((release/'latest.json').read_text('utf-8-sig'))
    tag=manifest['tag_name']
    if not re.fullmatch(r'v[0-9]+(?:\.[0-9]+){1,3}',tag):raise ValueError('Invalid version')
    files=[release/tag/name for name in [ASSET,ASSET+'.sig']]
    for file in files:
        asset=next(v for v in manifest['assets'] if v['name']==file.name)
        raw=file.read_bytes()
        if len(raw)!=asset['size'] or 'sha256:'+hashlib.sha256(raw).hexdigest()!=asset['digest']:
            raise ValueError('Release checksum mismatch')
    if not module.verify(bytes.fromhex(PUBLIC),files[0].read_bytes(),bytes.fromhex(files[1].read_text('ascii').strip())):
        raise ValueError('Release signature mismatch')
    if target:
        if (target/'latest.json').exists():
            old=json.loads((target/'latest.json').read_text('utf-8-sig'))['tag_name']
            if tuple(map(int,old.lstrip('v').split('.')))>tuple(map(int,tag[1:].split('.'))):
                raise ValueError('A newer private release is already published; downgrade refused')
        (target/tag).mkdir(parents=True,exist_ok=True)
        for file in files:
            destination=target/tag/file.name
            if destination.exists() and destination.read_bytes()!=file.read_bytes():
                raise ValueError('Published version already exists with different bytes')
            temporary=destination.with_name(destination.name+'.new')
            shutil.copy2(file,temporary);temporary.replace(destination)
        for name in ['notes.txt','latest.json']:
            temporary=target/(name+'.new')
            shutil.copy2(release/name,temporary);temporary.replace(target/name)
    print('Private release signature and checksums: OK'+('; published '+tag if target else ''))

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--release',type=Path)
    parser.add_argument('--target',type=Path)
    parser.add_argument('--check',action='store_true')
    parser.add_argument('--backup-config',type=Path)
    parser.add_argument('--backup',type=Path)
    args=parser.parse_args()
    if args.backup_config:
        config=json.loads(args.backup_config.read_text('utf-8-sig'))
        database=Path(config.get('database','data/lobby.sqlite3'))
        if not database.is_absolute():database=args.backup_config.parent/database
        if not database.is_file():raise FileNotFoundError('Configured room database missing')
        with closing(sqlite3.connect(database)) as source,closing(sqlite3.connect(args.backup)) as destination:source.backup(destination)
        print('Consistent room database snapshot saved.')
    else:install(args.release.resolve(),None if args.check else args.target.resolve())
