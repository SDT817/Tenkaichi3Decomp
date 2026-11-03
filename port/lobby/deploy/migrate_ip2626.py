"""Narrow, reversible directory URL migration. Never regenerate service keys.

SQLite's backup API provides a consistent backup without copying a live WAL.
Only the existing friends-main URL changes; all rooms/admins remain intact.
"""
import argparse
from contextlib import closing
import json
from pathlib import Path
import sqlite3

OLD = 'https://114-132-102-42.sslip.io'
NEW = 'https://114.132.102.42:2626'


def migrate(root, backup, restore=False):
    config_path = root / 'config/directory.json'
    config_bytes = config_path.read_bytes()
    config = json.loads(config_bytes.decode('utf-8-sig'))
    database = Path(config['database'])
    if not database.is_absolute():
        database = config_path.parent / database
    if not database.is_file():
        raise RuntimeError('Existing directory database not found; refusing to create one')
    backup.mkdir(parents=True, exist_ok=True)
    record = backup / 'directory-url-migration.json'
    if restore:
        saved = json.loads(record.read_text('utf-8'))
        target = saved['old_url']
        updated = (backup / 'directory.json').read_bytes()
    else:
        target = NEW
        for server in config.get('initial_servers', []):
            if server.get('id') == 'friends-main':
                if server.get('url') not in (OLD, NEW):
                    raise RuntimeError('Unexpected initial URL; original configuration was preserved')
                server['url'] = NEW
        updated = (json.dumps(config, ensure_ascii=False, indent=2)+'\n').encode('utf-8')
    with closing(sqlite3.connect(database, timeout=20)) as db, db:
        db.row_factory = sqlite3.Row
        row = db.execute("SELECT * FROM servers WHERE id='friends-main'").fetchone()
        if row is None or row['url'] not in (OLD, NEW):
            raise RuntimeError('Unexpected friends-main entry; existing custom server was preserved')
        if not restore and record.exists():
            raise RuntimeError('Backup record already exists; choose a new backup directory')
        if not restore:
            with closing(sqlite3.connect(backup / 'directory.sqlite3')) as snapshot:
                db.backup(snapshot)
            (backup / 'directory.json').write_bytes(config_bytes)
            record.write_text(json.dumps({'old_url': row['url'], 'new_url': NEW}, indent=2)+'\n', 'utf-8')
        db.execute('BEGIN IMMEDIATE')
        db.execute("UPDATE servers SET url=? WHERE id='friends-main'", (target,))
        after = dict(db.execute("SELECT * FROM servers WHERE id='friends-main'").fetchone())
        before = dict(row)
        before['url'] = target
        if before != after:
            raise RuntimeError('Directory fields other than URL changed')
    temporary = config_path.with_suffix('.json.ip2626.tmp')
    try:
        temporary.write_bytes(updated)
        temporary.replace(config_path)
    except OSError:
        with closing(sqlite3.connect(database, timeout=20)) as db, db:
            db.execute("UPDATE servers SET url=? WHERE id='friends-main' AND url=?", (row['url'], target))
        raise
    print('Existing directory URL restored.' if restore else 'Existing directory URL updated. Room database and administrator hashes preserved.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--backup', type=Path, required=True)
    parser.add_argument('--restore', action='store_true')
    args = parser.parse_args()
    migrate(args.root.resolve(), args.backup.resolve(), args.restore)
