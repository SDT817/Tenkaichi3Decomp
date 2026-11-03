#!/usr/bin/env python3
"""Persistent server directory and multiple administrators. No game simulation.

Public responses never contain administrator credentials or room access keys.
An administrator explicitly publishes a local favorite to this shared directory.
"""
import argparse
from contextlib import closing, contextmanager
import hashlib
import hmac
import ipaddress
import json
from pathlib import Path
import re
import secrets
import sqlite3
from http.server import ThreadingHTTPServer
from urllib.parse import urlsplit
from server import Refused, Lobby, MAX_ROOMS, compact, make_handler


def valid_url(value):
    if not isinstance(value, str) or not 1 <= len(value) <= 200 or any(c in value for c in '\r\n\t|\\ '):
        return False
    try:
        u = urlsplit(value)
        if not u.hostname or u.username or u.password or u.query or u.fragment or not u.port and u.netloc.endswith(':'):
            return False
        if u.scheme == 'https':
            return True
        if u.scheme != 'http':
            return False
        if u.hostname == 'localhost':
            return True
        ip = ipaddress.IPv4Address(u.hostname)
        return ip.is_loopback or ip in ipaddress.IPv4Network('10.0.0.0/8') or ip in ipaddress.IPv4Network('172.16.0.0/12') or ip in ipaddress.IPv4Network('192.168.0.0/16')
    except ValueError:
        return False


class Directory:
    def __init__(self, config):
        self.config = config
        self.database = str(config['database'])
        Path(self.database).parent.mkdir(parents=True, exist_ok=True)
        with self.db() as db:
            db.executescript('''PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS admins(id TEXT PRIMARY KEY,name TEXT NOT NULL,key_hash TEXT UNIQUE NOT NULL,active INTEGER NOT NULL DEFAULT 1);
                CREATE TABLE IF NOT EXISTS servers(id TEXT PRIMARY KEY,name TEXT NOT NULL,url TEXT UNIQUE NOT NULL,locked INTEGER NOT NULL DEFAULT 0,enabled INTEGER NOT NULL DEFAULT 1);
                CREATE TABLE IF NOT EXISTS meta(id INTEGER PRIMARY KEY,revision INTEGER NOT NULL);
                INSERT OR IGNORE INTO meta VALUES(1,0);''')
            first_run = not db.execute('SELECT 1 FROM admins').fetchone()
            if first_run:
                a = config.get('bootstrap_admin', {})
                if not re.fullmatch('[a-f0-9]{64}', a.get('key_hash', '')):
                    raise ValueError('Configure the initial administrator key hash')
                db.execute('INSERT INTO admins(id,name,key_hash) VALUES(?,?,?)',
                           (self.ident(a.get('id')), Lobby.text(a.get('name'), 64), a['key_hash']))
            for s in config.get('initial_servers', []) if first_run else []:
                if not valid_url(s.get('url')):
                    raise ValueError('Invalid initial server URL')
                db.execute('INSERT OR IGNORE INTO servers(id,name,url,locked) VALUES(?,?,?,?)',
                           (self.ident(s['id']), Lobby.text(s['name'], 64), s['url'].rstrip('/'), int(bool(s.get('locked')))))

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.database, timeout=5, isolation_level='IMMEDIATE')
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def ident(value):
        if not isinstance(value, str) or not re.fullmatch('[A-Za-z0-9_-]{1,32}', value):
            raise Refused('标识只能使用 1–32 个英文字母、数字、下划线或短横线。')
        return value

    def admin(self, db, headers):
        key = headers.get('x-bt3-lobby-key', '')
        if not re.fullmatch('[a-f0-9]{64}', key):
            raise Refused('管理员凭据无效。')
        hashed = hashlib.sha256(key.encode()).hexdigest()
        a = db.execute('SELECT * FROM admins WHERE key_hash=? AND active=1', (hashed,)).fetchone()
        if not a:
            raise Refused('管理员凭据无效或已撤销。')
        return a

    def listing(self, db, admin=False):
        return {'directory': self.config.get('name', '服务器目录'), 'api': 1,
                'revision': db.execute('SELECT revision FROM meta').fetchone()[0],
                'servers': [{**dict(r), 'locked': bool(r['locked']), 'enabled': bool(r['enabled'])} for r in db.execute(
                    'SELECT * FROM servers'+('' if admin else ' WHERE enabled=1')+' ORDER BY id')]}

    def room_settings(self, body=None):
        database = self.config.get('lobby_database')
        if not database:
            if body is not None:
                raise Refused('此目录尚未启用房间管理，请先更新服务端。')
            return {}
        with closing(sqlite3.connect(Path(database).resolve().as_uri()+'?mode=rw', uri=True, timeout=5)) as db, db:
            db.row_factory = sqlite3.Row
            if body is not None:
                if body.get('server') != self.config.get('lobby_server_id'):
                    raise Refused('请选择此目录管理的服务器。')
                db.execute('BEGIN IMMEDIATE')
                op = body.get('op')
                if op == 'add_room':
                    if db.execute('SELECT count(*) FROM rooms WHERE enabled=1').fetchone()[0] >= MAX_ROOMS:
                        raise Refused('最多可以添加 32 个房间。')
                    ident = 'room-' + secrets.token_hex(8)
                    name = Lobby.text(body.get('name'), 64)
                    rules = Lobby.rules({})
                    db.execute('INSERT INTO room_names(id,name,added) VALUES(?,?,1)', (ident, name))
                    db.execute('INSERT INTO room_rules(id,rules) VALUES(?,?)', (ident, compact(rules)))
                    db.execute('INSERT INTO rooms(id,name,rules,epoch) VALUES(?,?,?,?)',
                               (ident, name, compact(rules), secrets.token_hex(16)))
                else:
                    row = db.execute('SELECT * FROM rooms WHERE id=? AND enabled=1', (body.get('room'),)).fetchone()
                    if not row:
                        raise Refused('此房间不存在或已停用。')
                    if row['phase'] != 'idle':
                        raise Refused('连接或对战期间不能修改房间，请等待双方返回房间。')
                    if op == 'rename_room':
                        name = Lobby.text(body.get('name'), 64)
                        db.execute('INSERT INTO room_names(id,name) VALUES(?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name',
                                   (row['id'], name))
                        db.execute('UPDATE rooms SET name=?,epoch=? WHERE id=?', (name, secrets.token_hex(16), row['id']))
                    else:
                        values = body.get('rules')
                        if not isinstance(values, dict) or set(values) != {'battle', 'time', 'speed'}:
                            raise Refused('请选择有效的模式、时限和速度。')
                        rules = Lobby.rules({**json.loads(row['rules']), **values})
                        db.execute('INSERT INTO room_rules(id,rules) VALUES(?,?) ON CONFLICT(id) DO UPDATE SET rules=excluded.rules',
                                   (row['id'], compact(rules)))
                        db.execute('UPDATE rooms SET rules=?,epoch=? WHERE id=?', (compact(rules), secrets.token_hex(16), row['id']))
            return {'server': self.config.get('lobby_server_id', ''),
                    'rooms': [{'id': r['id'], 'name': r['name'], 'phase': r['phase'], 'rules': json.loads(r['rules'])}
                              for r in db.execute('SELECT * FROM rooms WHERE enabled=1 ORDER BY id')]}

    def request(self, path, body, headers=None, ip=None):
        try:
            if path != '/directory/v1/request' or not isinstance(body, dict):
                raise Refused('目录请求无效。')
            headers = {k.lower(): v for k, v in (headers or {}).items()}
            with self.db() as db:
                op = body.get('op')
                if op == 'list':
                    return {'ok': True, **self.listing(db)}
                a = self.admin(db, headers)
                if op == 'whoami':
                    return {'ok': True, 'admin': {'id': a['id'], 'name': a['name']},
                            'admins': [dict(r) for r in db.execute('SELECT id,name,active FROM admins ORDER BY id')],
                            'room_settings': self.room_settings(),
                            **self.listing(db, True)}
                if op in ('save_room', 'rename_room', 'add_room'):
                    return {'ok': True, 'room_settings': self.room_settings(body)}
                if op == 'rename':
                    ident = self.ident(body.get('id'))
                    row = db.execute('SELECT * FROM servers WHERE id=? AND url=?', (ident, body.get('url'))).fetchone()
                    if not row:
                        raise Refused('服务器地址已更新，请刷新目录后重试。')
                    db.execute('UPDATE servers SET name=? WHERE id=?', (Lobby.text(body.get('name'), 64), ident))
                elif op == 'publish':
                    ident = self.ident(body.get('id'))
                    if not valid_url(body.get('url')) or type(body.get('locked', False)) is not bool:
                        raise Refused('服务器地址或访问设置无效。')
                    if not db.execute('SELECT 1 FROM servers WHERE id=?', (ident,)).fetchone() and db.execute('SELECT count(*) FROM servers').fetchone()[0] >= 64:
                        raise Refused('目录最多容纳 64 台服务器。')
                    db.execute('''INSERT INTO servers(id,name,url,locked,enabled) VALUES(?,?,?,?,1)
                        ON CONFLICT(id) DO UPDATE SET name=excluded.name,url=excluded.url,locked=excluded.locked,enabled=1''',
                        (ident, Lobby.text(body.get('name'), 64), body['url'].rstrip('/'), int(body.get('locked', False))))
                elif op in ('unpublish', 'remove'):
                    ident = self.ident(body.get('id'))
                    if op == 'remove':
                        db.execute('DELETE FROM servers WHERE id=?', (ident,))
                    else:
                        db.execute('UPDATE servers SET enabled=0 WHERE id=?', (ident,))
                elif op == 'add_admin':
                    ident = self.ident(body.get('id'))
                    if db.execute('SELECT count(*) FROM admins').fetchone()[0] >= 32:
                        raise Refused('管理员数量已达上限。')
                    key = secrets.token_hex(32)
                    db.execute('INSERT INTO admins(id,name,key_hash) VALUES(?,?,?)',
                               (ident, Lobby.text(body.get('name'), 64), hashlib.sha256(key.encode()).hexdigest()))
                    return {'ok': True, 'id': ident, 'key': key}  # shown once to the administering user
                elif op == 'revoke_admin':
                    ident = self.ident(body.get('id'))
                    if ident == a['id']:
                        raise Refused('请由另一位管理员撤销此账号，避免误失去管理权限。')
                    db.execute('UPDATE admins SET active=0 WHERE id=?', (ident,))
                else:
                    raise Refused('未知目录操作。')
                db.execute('UPDATE meta SET revision=revision+1')
                return {'ok': True, **self.listing(db, True)}
        except (Refused, sqlite3.IntegrityError) as e:
            return {'ok': False, 'error': '标识或地址已存在。' if isinstance(e, sqlite3.IntegrityError) else str(e)}


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--config', type=Path, default=Path(__file__).with_name('directory.json'))
    args = p.parse_args()
    config = json.loads(args.config.read_text('utf-8-sig'))
    database = Path(config.get('database', 'data/directory.sqlite3'))
    config['database'] = str(database if database.is_absolute() else args.config.resolve().parent/database)
    if config.get('lobby_database'):
        database = Path(config['lobby_database'])
        config['lobby_database'] = str(database if database.is_absolute() else args.config.resolve().parent/database)
    service = Directory(config)
    server = ThreadingHTTPServer((config.get('listen', '127.0.0.1'), config.get('port', 8788)), make_handler(service))
    server.daemon_threads = True
    print('BT3 directory: http://%s:%s (local test; no public deployment)' % server.server_address, flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
