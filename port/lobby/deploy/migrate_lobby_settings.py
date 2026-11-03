"""Connect directory administration to the existing local room database."""
import argparse
from contextlib import closing
import json
from pathlib import Path
import re
import sqlite3
from urllib.parse import urlsplit


def database(config_path, config):
    value = Path(config['database'])
    return value if value.is_absolute() else config_path.parent/value


def endpoint(value):
    if not isinstance(value, str):
        raise ValueError('Invalid installed endpoint')
    parsed = urlsplit(value)
    if (parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or
        parsed.query or parsed.fragment or any(c.isspace() for c in value)):
        raise ValueError('Invalid installed endpoint')
    return (parsed.scheme, parsed.hostname.lower(), parsed.port or 443, parsed.path.rstrip('/'))


def local_entry(db, directory, rooms, url):
    existing = db.execute('SELECT id,name,url,enabled,locked FROM servers ORDER BY id').fetchall()
    matches = []
    for row in existing:
        try:
            if endpoint(row['url']) == endpoint(url):matches.append(dict(row))
        except ValueError:
            pass
    if len(matches) > 1:
        raise RuntimeError('Multiple directory entries match the installed endpoint; configuration preserved')
    if matches:
        return matches[0], False
    # A removed directory entry must not prevent configuring the local service.
    # Recreate only this installation's endpoint; never change other entries.
    seed = {}
    for item in directory.get('initial_servers', []):
        try:
            if endpoint(item.get('url')) == endpoint(url):seed = item;break
        except ValueError:
            pass
    ident = seed.get('id', 'friends-main')
    if not isinstance(ident, str) or not re.fullmatch('[A-Za-z0-9_-]{1,32}', ident):ident = 'friends-main'
    ids = {r['id'] for r in existing}
    if ident in ids:
        ident = 'local-ip2626'
        for suffix in range(65):
            candidate = ident if suffix == 0 else ident+'-'+str(suffix)
            if candidate not in ids:ident = candidate;break
        else:raise RuntimeError('No unused directory ID available; configuration preserved')
    if len(existing) >= 64:
        raise RuntimeError('Directory is full; missing local entry was not added')
    name = rooms.get('name', seed.get('name', 'BT3 server'))
    if (not isinstance(name, str) or not name.strip() or len(name.encode('utf-8')) > 64 or
        any(ord(c) < 32 for c in name)):
        raise RuntimeError('Invalid local server name; configuration preserved')
    return {'id':ident,'name':name.strip(),'url':url.rstrip('/'),
            'enabled':1,'locked':int(bool(rooms.get('access_key')))}, True


def migrate(root, backup=None, check=False):
    room_path = root/'config/server.json'
    directory_path = root/'config/directory.json'
    rooms = json.loads(room_path.read_text('utf-8-sig'))
    directory = json.loads(directory_path.read_text('utf-8-sig'))
    room_database = database(room_path,rooms).resolve()
    directory_database = database(directory_path,directory).resolve()
    record = json.loads((root/'config/ip2626-deployment.json').read_text('utf-8-sig'))
    url = record.get('url')
    endpoint(url)
    for source in (room_database,directory_database):
        if not source.is_file():raise RuntimeError('Existing database missing; refusing to create a new one')
    with closing(sqlite3.connect(directory_database.as_uri()+'?mode=rw',uri=True,timeout=5)) as db:
        db.row_factory = sqlite3.Row
        chosen, recovered = local_entry(db,directory,rooms,url)
        if check:
            print('Room administration preflight: OK. Local directory ID: '+chosen['id']+
                  (' (missing entry will be restored).' if recovered else ' (existing entry retained).'))
            return
        if backup is None:raise RuntimeError('Backup directory required')
        for source,name in ((room_database,'rooms.sqlite3'),(directory_database,'directory.sqlite3')):
            with closing(sqlite3.connect(source.as_uri()+'?mode=rw',uri=True)) as snapshot_source:
                with closing(sqlite3.connect(backup/name)) as snapshot:snapshot_source.backup(snapshot)
        with db:
            db.execute('BEGIN IMMEDIATE')
            chosen, recovered = local_entry(db,directory,rooms,url)
            if recovered:
                db.execute('INSERT INTO servers(id,name,url,enabled,locked) VALUES(?,?,?,?,?)',
                           tuple(chosen[k] for k in ('id','name','url','enabled','locked')))
                db.execute('UPDATE meta SET revision=revision+1')
            directory['lobby_database'] = str(room_database)
            directory['lobby_server_id'] = chosen['id']
            for room in rooms['rooms']:
                room.setdefault('rules',{})['speed'] = 100
            for path,value in ((room_path,rooms),(directory_path,directory)):
                temporary = path.with_suffix('.settings.tmp')
                temporary.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n','utf-8')
                temporary.replace(path)
        if recovered:print('Missing local directory entry restored: '+chosen['id'])
    print('Room administration enabled. Configured room speed: 100%. Existing administrator identities and rooms preserved.')


if __name__=='__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--backup',type=Path)
    parser.add_argument('--check',action='store_true')
    args = parser.parse_args()
    migrate(args.root.resolve(),args.backup.resolve() if args.backup else None,args.check)
