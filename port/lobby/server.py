#!/usr/bin/env python3
"""Persistent eight-seat lobby; introduces peers to the unmodified BT3 protocol 6.

Only the control plane is HTTP. UDP is handled by the game's existing TURN
client and coturn. No ISO, game assets, or battle simulation are used here.
Run with Python 3.11+. No third-party packages are required for the demo.
"""
import argparse
from contextlib import contextmanager
import base64
import hashlib
import hmac
import ipaddress
import json
import logging
import os
from pathlib import Path
import re
import secrets
import sqlite3
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PROTOCOL = 6
LEASE = 10
START_TIMEOUT = 90
FINISH_TIMEOUT = 10
MATCH_LIFETIME = 8 * 3600
MAX_ROOMS = 32
SLOTS = 8


class Refused(Exception):
    pass


def digest(token):
    return hashlib.sha256(token.encode()).hexdigest()


def compact(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'))


class Lobby:
    def __init__(self, config, clock=time.time):
        self.config = config
        self.clock = clock
        self.database = str(config['database'])
        self.secret = config['secret'].encode()
        self.access = config.get('access_key', '')
        if not isinstance(self.access, str) or len(self.access) > 96 or any(ord(c) < 33 or ord(c) > 126 or c == '|' for c in self.access):
            raise ValueError('access_key: use at most 96 printable ASCII characters, without |')
        self.turn = config.get('turn', {})
        self.relay_only = bool(self.turn.get('required', False))
        if self.relay_only and not (self.turn.get('server') and self.turn.get('secret')):
            raise ValueError('TURN required: set turn.server and turn.secret')
        rooms = config['rooms']
        if not 1 <= len(rooms) <= MAX_ROOMS:
            raise ValueError('Configure 1..32 permanent rooms')
        Path(self.database).parent.mkdir(parents=True, exist_ok=True)
        with self.db() as db:
            db.executescript('''
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS rooms (
                    id TEXT PRIMARY KEY, name TEXT NOT NULL, rules TEXT NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 1, epoch TEXT NOT NULL DEFAULT '', session TEXT NOT NULL DEFAULT '',
                    phase TEXT NOT NULL DEFAULT 'idle', started REAL NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS room_names (id TEXT PRIMARY KEY, name TEXT NOT NULL, added INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS room_rules (id TEXT PRIMARY KEY, rules TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS members (
                    token TEXT PRIMARY KEY, room TEXT NOT NULL, name TEXT NOT NULL,
                    seat INTEGER NOT NULL DEFAULT 0, ready INTEGER NOT NULL DEFAULT 0,
                    expires REAL NOT NULL);
                CREATE UNIQUE INDEX IF NOT EXISTS occupied ON members(room,seat) WHERE seat>0;
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY, room TEXT NOT NULL, p1 TEXT NOT NULL, p2 TEXT NOT NULL,
                    made REAL NOT NULL, code TEXT UNIQUE, host_key TEXT NOT NULL,
                    join_key TEXT NOT NULL, host_name TEXT, join_name TEXT,
                    host_addrs TEXT, join_addrs TEXT, host_ip TEXT, join_ip TEXT,
                    ended1 INTEGER NOT NULL DEFAULT 0, ended2 INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS spectators (
                    session TEXT NOT NULL, token TEXT NOT NULL, seat INTEGER NOT NULL,
                    key TEXT NOT NULL, addrs TEXT, ended INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY(session,token));
            ''')
            if 'epoch' not in [r['name'] for r in db.execute('PRAGMA table_info(rooms)')]:
                db.execute("ALTER TABLE rooms ADD COLUMN epoch TEXT NOT NULL DEFAULT ''")
            columns = {r['name'] for r in db.execute('PRAGMA table_info(members)')}
            for column, sql in [('view', "TEXT NOT NULL DEFAULT 'full'"), ('ping', 'INTEGER NOT NULL DEFAULT -1'),
                                ('ping_at', 'REAL NOT NULL DEFAULT 0'), ('swap_at', 'REAL NOT NULL DEFAULT 0')]:
                if column not in columns:
                    db.execute(f'ALTER TABLE members ADD COLUMN {column} {sql}')
            if 'view' not in {r['name'] for r in db.execute('PRAGMA table_info(sessions)')}:
                db.execute("ALTER TABLE sessions ADD COLUMN view TEXT NOT NULL DEFAULT 'full'")
            if 'sync_pause' not in {r['name'] for r in db.execute('PRAGMA table_info(members)')}:
                db.execute("ALTER TABLE members ADD COLUMN sync_pause INTEGER NOT NULL DEFAULT 0")
            if 'version' not in {r['name'] for r in db.execute('PRAGMA table_info(members)')}:
                db.execute("ALTER TABLE members ADD COLUMN version TEXT NOT NULL DEFAULT ''")
            columns = {r['name'] for r in db.execute('PRAGMA table_info(sessions)')}
            for column, sql in [('launched', 'INTEGER NOT NULL DEFAULT 0'),
                                ('finished_at', 'REAL NOT NULL DEFAULT 0')]:
                if column not in columns:
                    db.execute(f'ALTER TABLE sessions ADD COLUMN {column} {sql}')
            for table in ('rooms', 'sessions'):
                if 'allow_pause' not in {r['name'] for r in db.execute(f'PRAGMA table_info({table})')}:
                    db.execute(f"ALTER TABLE {table} ADD COLUMN allow_pause INTEGER NOT NULL DEFAULT 1")
            db.execute('UPDATE rooms SET enabled=0')
            ids = set()
            for r in [*rooms, *[dict(r) for r in db.execute('SELECT id,name FROM room_names WHERE added=1') if r['id'] not in {v['id'] for v in rooms}]]:
                ident = r['id']
                if not re.fullmatch(r'[A-Za-z0-9_-]{1,32}', ident) or ident in ids:
                    raise ValueError('Room IDs must be unique ASCII identifiers')
                ids.add(ident)
                saved = db.execute('SELECT rules FROM room_rules WHERE id=?', (ident,)).fetchone()
                rules = self.rules(json.loads(saved['rules']) if saved else r.get('rules', {}))
                saved_name = db.execute('SELECT name FROM room_names WHERE id=?', (ident,)).fetchone()
                name = self.text(saved_name['name'] if saved_name else r['name'], 64)
                db.execute('''INSERT INTO rooms(id,name,rules) VALUES(?,?,?)
                    ON CONFLICT(id) DO UPDATE SET name=excluded.name,rules=excluded.rules,enabled=1''',
                    (ident, name, compact(rules)))
            # Permanent definitions survive; no session/seat from a dead service is reused.
            db.execute('DELETE FROM members')
            db.execute('DELETE FROM sessions')
            db.execute('DELETE FROM spectators')
            db.execute("UPDATE rooms SET session='',phase='idle',started=0,epoch=?", (secrets.token_hex(16),))

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
    def rules(values):
        rules = {'battle': 0, 'time': 4, 'speed': 100, 'rollback': 8, 'delay': -2}
        if not isinstance(values, dict) or values.keys()-rules.keys():
            raise Refused('房间规则无效。')
        rules.update(values)
        if (any(type(v) is not int for v in rules.values()) or
            not 0 <= rules['battle'] <= 4 or not 0 <= rules['time'] <= 4 or
            not 100 <= rules['speed'] <= 150 or rules['rollback'] not in (0, 2, 4, 6, 8) or
            rules['delay'] not in (-2, 0, 1, 2, 3, 4, 5, 6)):
            raise Refused('房间规则无效。')
        return rules

    @staticmethod
    def text(value, limit):
        if (not isinstance(value, str) or not value.strip() or len(value.encode('utf-8')) > limit or
            any(ord(c) < 32 for c in value)):
            raise Refused('文本为空、过长或包含无效字符。')
        return value.strip()

    @staticmethod
    def version_key(version):
        # Same numeric comparison as the updater (missing components are zero).
        if not isinstance(version, str) or not re.fullmatch(r"[0-9]{1,9}(?:\.[0-9]{1,9}){1,3}", version):
            raise Refused('客户端版本号无效，请更新游戏。')
        parts = tuple(map(int, version.split('.')))
        return parts + (0,) * (4-len(parts))

    @staticmethod
    def member_version(member):
        # Released 0.13/0.14 clients predate the explicit version field.
        return member['version'] or ('0.14' if member['sync_pause'] else '0.13')

    def authorized(self, headers):
        if self.access and not hmac.compare_digest(headers.get('x-bt3-lobby-key', '').encode('utf-8'), self.access.encode('utf-8')):
            raise Refused('服务器访问口令不正确。')

    def clean(self, db):
        now = self.clock()
        expired = db.execute('SELECT DISTINCT room FROM members WHERE expires<=?', (now,)).fetchall()
        db.execute('DELETE FROM members WHERE expires<=?', (now,))
        for r in expired:
            row = db.execute('SELECT phase FROM rooms WHERE id=?', (r['room'],)).fetchone()
            if row and row['phase'] == 'idle':
                self.reset(db, r['room'])  # invalidate a Start click against an old occupancy
        db.execute('UPDATE spectators SET ended=1 WHERE token NOT IN (SELECT token FROM members)')
        # Repair every locked room, including a previously stranded one-player room.
        # A spectator leaving cannot end the two players' match.
        for row in db.execute("SELECT * FROM rooms WHERE phase IN ('starting','playing')").fetchall():
            s = db.execute('SELECT * FROM sessions WHERE id=?', (row['session'],)).fetchone()
            missing = not s or any(not db.execute('SELECT 1 FROM members WHERE token=? AND room=? AND seat=?',
                (s['p'+str(n)], row['id'], n)).fetchone() for n in (1, 2))
            incomplete = s and s['launched'] != 3 and row['started'] <= now-START_TIMEOUT
            finishing = s and s['finished_at'] > 0 and s['finished_at'] <= now-FINISH_TIMEOUT
            if missing or incomplete or finishing or row['started'] <= now-MATCH_LIFETIME:
                self.reset(db, row['id'])
        db.execute('DELETE FROM sessions WHERE made<?', (now - MATCH_LIFETIME,))
        db.execute('DELETE FROM spectators WHERE session NOT IN (SELECT id FROM sessions)')

    @staticmethod
    def reset(db, room):
        db.execute("UPDATE rooms SET session='',phase='idle',started=0,epoch=? WHERE id=?", (secrets.token_hex(16), room))
        db.execute('UPDATE members SET ready=(seat>0) WHERE room=?', (room,))

    def end_if_done(self, db, session):
        s = db.execute('SELECT * FROM sessions WHERE id=?', (session,)).fetchone()
        if not s:
            return
        # Once one side has returned, never wait forever for a lost Finish request.
        if s['ended1'] or s['ended2']:
            db.execute('UPDATE sessions SET finished_at=? WHERE id=? AND finished_at=0', (self.clock(), session))
        missing = any(not db.execute('SELECT 1 FROM members WHERE token=? AND room=? AND seat=?',
            (s['p'+str(n)], s['room'], n)).fetchone() for n in (1, 2))
        if missing or (s['ended1'] and s['ended2']):
            active = db.execute('SELECT session FROM rooms WHERE id=?', (s['room'],)).fetchone()
            if active and active['session'] == session:
                self.reset(db, s['room'])

    def member(self, db, body):
        raw = body.get('token', '')
        if not isinstance(raw, str) or not re.fullmatch('[a-f0-9]{48}', raw):
            raise Refused('房间身份已失效，请重新进入。')
        m = db.execute('SELECT * FROM members WHERE token=?', (digest(raw),)).fetchone()
        if not m:
            raise Refused('房间身份已失效，请重新进入。')
        db.execute('UPDATE members SET expires=? WHERE token=?', (self.clock() + LEASE, m['token']))
        return m

    def match_token(self, session, member, seat):
        return hmac.new(self.secret, f'{session}:{member}:{seat}'.encode(), hashlib.sha256).hexdigest()

    def view(self, db, room, member=None):
        r = db.execute('SELECT * FROM rooms WHERE id=? AND enabled=1', (room,)).fetchone()
        if not r:
            raise Refused('此房间不存在或已停用。')
        people = db.execute('SELECT * FROM members WHERE room=? AND seat>0 ORDER BY seat', (room,)).fetchall()
        out = {'id': r['id'], 'name': r['name'], 'phase': r['phase'], 'session': r['session'], 'epoch': r['epoch'],
               'allow_pause': r['allow_pause'], 'rules': json.loads(r['rules']), 'seats': [{'seat': n, 'name': '', 'ready': False} for n in range(1, SLOTS+1)]}
        for p in people:
            out['seats'][p['seat']-1] = {'seat': p['seat'], 'name': p['name'], 'ready': bool(p['ready']),
                'view': p['view'], 'version': self.member_version(p),
                'ping': p['ping'] if self.clock()-p['ping_at'] < 10 else -1}
        players = [p for p in people if p['seat'] in (1, 2)]
        out['mode_match'] = len(players) == 2 and players[0]['view'] == players[1]['view']
        out['clients_current'] = all(p['sync_pause'] for p in people)
        versions = {self.version_key(self.member_version(p)) for p in people}
        out['versions_match'] = len(versions) <= 1
        out['can_start'] = r['phase'] == 'idle' and out['mode_match'] and out['clients_current'] and out['versions_match']
        if member:
            out['me'] = member['seat']
            out['ready'] = bool(member['ready'])
            out['view'] = member['view']
            out['swap_wait_ms'] = max(0, int((member['swap_at']+1-self.clock())*1000))
            ping = self.config.get('ping', {})
            if ping.get('host') and ping.get('port'):
                out['probe'] = {'host': ping['host'], 'port': ping['port'],
                    'key': hmac.new(self.secret, ('ping:'+member['token']).encode(), hashlib.sha256).hexdigest()}
            if r['session'] and member['seat']:
                s = db.execute('SELECT * FROM sessions WHERE id=?', (r['session'],)).fetchone()
                watch = db.execute('SELECT * FROM spectators WHERE session=? AND token=?', (r['session'], member['token'])).fetchone()
                player = s and member['seat'] in (1, 2) and s['p'+str(member['seat'])] == member['token']
                if s and (player or watch):
                    out['match_token'] = self.match_token(s['id'], member['token'], member['seat'])
                    usable = not self.relay_only or (s['host_addrs'] and any(a.startswith('relay=') for a in json.loads(s['host_addrs'])))
                    out['code'] = (s['code'] or '') if usable else ''
                    out['ended'] = bool(s['ended'+str(member['seat'])] if player else watch['ended'])
                    out['match_view'] = s['view']
                    out['match_pause'] = s['allow_pause']
        return out

    def lobby(self, db, body, headers):
        self.authorized(headers)
        op = body.get('op', '')
        if op == 'list':
            return {'server': self.config.get('name', 'BT3'), 'api': 2, 'protocol': PROTOCOL,
                    'relay_only': self.relay_only, 'turn_available': bool(self.turn.get('server')), 'slots': SLOTS, 'edition': '0.16',
                    'rooms': [self.view(db, r['id']) for r in
                              db.execute('SELECT id FROM rooms WHERE enabled=1 ORDER BY id').fetchall()]}
        if op == 'enter':
            room = self.text(body.get('room'), 32)
            state = self.view(db, room)
            if state['phase'] != 'idle':
                raise Refused('此房间正在连接或对战。')
            preferred = body.get('seat', 0)
            if type(preferred) is not int or preferred not in range(SLOTS+1):
                raise Refused('座位无效。')
            seat = next((s['seat'] for s in state['seats'] if not s['name'] and (not preferred or preferred == s['seat'])), 0)
            if not seat:
                raise Refused('房间已满，请选择其他房间。')
            if db.execute('SELECT count(*) FROM members').fetchone()[0] >= 128:
                raise Refused('大厅暂时已满，请稍后重试。')
            token = secrets.token_hex(24)
            capable = int(type(body.get('sync_pause')) is int and body['sync_pause'] == 1)
            version = body.get('version', '0.14' if capable else '0.13')
            self.version_key(version)
            db.execute('INSERT INTO members(token,room,name,expires,seat,ready,sync_pause,version) VALUES(?,?,?,?,?,1,?,?)',
                       (digest(token), room, self.text(body.get('name', 'Player'), 64), self.clock()+LEASE, seat, capable, version))
            db.execute('UPDATE rooms SET epoch=? WHERE id=?', (secrets.token_hex(16), room))
            return {'token': token, 'room': self.view(db, room, db.execute('SELECT * FROM members WHERE token=?', (digest(token),)).fetchone())}
        m = self.member(db, body)
        r = db.execute('SELECT * FROM rooms WHERE id=? AND enabled=1', (m['room'],)).fetchone()
        if not r:
            raise Refused('此房间已停用，请退出。')
        if op == 'leave':
            if r['phase'] == 'starting' and m['seat'] in (1, 2):
                self.reset(db, r['id'])
            elif r['phase'] == 'playing' and m['seat'] in (1, 2):
                self.reset(db, r['id'])  # a fixed two-player match cannot keep a departed player
            elif r['phase'] == 'idle':
                self.reset(db, r['id'])
            db.execute('DELETE FROM members WHERE token=?', (m['token'],))
            db.execute('UPDATE members SET ready=(seat>0) WHERE room=?', (m['room'],))
            return {}
        if op == 'seat':
            seat = body.get('seat')
            if type(seat) is not int or seat not in range(SLOTS+1):
                raise Refused('座位无效。')
            if r['phase'] != 'idle':
                raise Refused('连接或对战期间不能换位。')
            if seat and db.execute('SELECT 1 FROM members WHERE room=? AND seat=? AND token<>?',
                                    (m['room'], seat, m['token'])).fetchone():
                raise Refused('这个位置已经有人了，请选择另一个位置。')
            db.execute('UPDATE members SET seat=? WHERE token=?', (seat, m['token']))
            self.reset(db, m['room'])
        elif op == 'swap':
            seat = body.get('seat')
            if type(seat) is not int or seat not in range(1, SLOTS+1) or seat == m['seat'] or not m['seat']:
                raise Refused('请选择其他玩家的位置。')
            if r['phase'] != 'idle':
                raise Refused('连接或对战期间不能换座。')
            other = db.execute('SELECT * FROM members WHERE room=? AND seat=?', (m['room'], seat)).fetchone()
            if not other:
                raise Refused('对方已离开，请刷新房间。')
            now = self.clock()
            if now < max(m['swap_at'], other['swap_at'])+1:
                raise Refused('换座冷却中，请稍后再试。')
            # BEGIN IMMEDIATE serializes both requests. Free one unique seat,
            # exchange atomically, then cool down BOTH affected players.
            db.execute('UPDATE members SET seat=0 WHERE token=?', (m['token'],))
            db.execute('UPDATE members SET seat=?,swap_at=? WHERE token=?', (m['seat'], now, other['token']))
            db.execute('UPDATE members SET seat=?,swap_at=? WHERE token=?', (seat, now, m['token']))
            self.reset(db, m['room'])
        elif op == 'mode':
            if r['phase'] != 'idle' or not m['seat']:
                raise Refused('请先就位，连接或对战期间不能切换模式。')
            if body.get('view') not in ('full', 'split'):
                raise Refused('联机模式无效。')
            db.execute('UPDATE members SET view=? WHERE token=?', (body['view'], m['token']))
            db.execute('UPDATE rooms SET epoch=? WHERE id=?', (secrets.token_hex(16), m['room']))
        elif op == 'pause':
            if r['phase'] != 'idle' or m['seat'] not in (1, 2):
                raise Refused('只有已就位的对战玩家可在开始前修改暂停选项。')
            if type(body.get('allow')) is not int or body['allow'] not in (0, 1):
                raise Refused('暂停选项无效。')
            db.execute('UPDATE rooms SET allow_pause=?,epoch=? WHERE id=?',
                       (body['allow'], secrets.token_hex(16), m['room']))
        elif op == 'start':
            if r['phase'] != 'idle' or m['seat'] not in (1, 2):
                raise Refused('请先就位 1P 或 2P，或等待双方返回房间。')
            if body.get('epoch', '') != r['epoch']:
                raise Refused('房间状态已更新，请重试。')
            players = db.execute('SELECT * FROM members WHERE room=? AND seat IN (1,2) AND ready=1 ORDER BY seat', (m['room'],)).fetchall()
            if len(players) != 2:
                raise Refused('需要两位玩家都已就位才能开始。')
            if players[0]['view'] != players[1]['view']:
                raise Refused('双方联机模式不一致，请选择相同模式后开始。')
            if not self.view(db, m['room'])['versions_match']:
                raise Refused('玩家版本不同，无法开始。低版本玩家请先更新游戏并重新进入房间。')
            if db.execute('SELECT 1 FROM members WHERE room=? AND seat>0 AND sync_pause=0', (m['room'],)).fetchone():
                raise Refused('请所有已就位玩家（含观众）升级到 0.14 或更新版本后开始。')
            session = secrets.token_hex(16)
            db.execute('''INSERT INTO sessions(id,room,p1,p2,made,host_key,join_key,view,allow_pause) VALUES(?,?,?,?,?,?,?,?,?)''',
                       (session, m['room'], players[0]['token'], players[1]['token'], self.clock(), secrets.token_hex(16), secrets.token_hex(16), players[0]['view'], r['allow_pause']))
            for spectator in db.execute('SELECT * FROM members WHERE room=? AND seat>2', (m['room'],)).fetchall():
                db.execute('INSERT INTO spectators(session,token,seat,key) VALUES(?,?,?,?)',
                           (session, spectator['token'], spectator['seat'], secrets.token_hex(16)))
            db.execute("UPDATE rooms SET session=?,phase='starting',started=? WHERE id=?", (session, self.clock(), m['room']))
        elif op in ('launch', 'finish', 'cancel'):
            session = body.get('session', '')
            if not session or session != r['session']:
                return {'room': self.view(db, m['room'], m)}  # late response cannot reset a new match
            if not m['seat']:
                raise Refused('请先选位。')
            if m['seat'] > 2:
                if op in ('finish', 'cancel'):
                    db.execute('UPDATE spectators SET ended=1 WHERE session=? AND token=?', (session, m['token']))
            elif op == 'launch':
                db.execute('UPDATE sessions SET launched=launched|? WHERE id=?', (1 << (m['seat']-1), session))
                if r['phase'] == 'starting':
                    db.execute("UPDATE rooms SET phase='playing' WHERE id=?", (m['room'],))
            elif op == 'cancel' and r['phase'] == 'starting':
                self.reset(db, m['room'])
            else:
                db.execute('UPDATE sessions SET ended%d=1 WHERE id=?' % m['seat'], (session,))
                db.execute('UPDATE members SET ready=(seat>0) WHERE token=?', (m['token'],))
                self.end_if_done(db, session)
        elif op != 'poll':
            raise Refused('未知大厅操作。')
        m = db.execute('SELECT * FROM members WHERE token=?', (m['token'],)).fetchone()
        return {'room': self.view(db, m['room'], m)}

    def match_auth(self, db, headers):
        auth = headers.get('x-bt3-room', '')
        if not re.fullmatch('[a-f0-9]{64}', auth):
            raise Refused('room authorization required')
        for s in db.execute("SELECT sessions.* FROM sessions JOIN rooms ON rooms.session=sessions.id WHERE rooms.phase IN ('starting','playing')").fetchall():
            for seat in (1, 2):
                if hmac.compare_digest(auth, self.match_token(s['id'], s['p'+str(seat)], seat)):
                    return s, seat
            for w in db.execute('SELECT * FROM spectators WHERE session=? AND ended=0', (s['id'],)).fetchall():
                if hmac.compare_digest(auth, self.match_token(s['id'], w['token'], w['seat'])):
                    return s, w['seat']
        raise Refused('room authorization expired')

    def turn_login(self, s):
        if not self.turn.get('server'):
            return {'noRelay': 'Local demo: direct connections only'}
        # Coturn REST authentication; no shared secret is ever sent to a client.
        username = f"{int(self.clock()) + MATCH_LIFETIME + 3600}:{s['id']}"
        credential = base64.b64encode(hmac.new(self.turn['secret'].encode(), username.encode(), hashlib.sha1).digest()).decode()
        return {'turn': {'server': self.turn['server'], 'username': username, 'credential': credential}}

    @staticmethod
    def addresses(raw, ip):
        if not isinstance(raw, list) or len(raw) > 4:
            raise Refused('bad request: addresses')
        result = []
        for value in raw:
            if not isinstance(value, str) or len(value) > 63:
                raise Refused('bad request: address')
            relay = value.startswith('relay=')
            addr = value[6:] if relay else value
            match = re.fullmatch(r'([0-9.]+):([0-9]{1,5})', addr)
            try:
                valid = bool(match and ipaddress.IPv4Address(match[1]) and 1 <= int(match[2]) <= 65535)
            except ipaddress.AddressValueError:
                valid = False
            if not valid:
                raise Refused('bad request: address')
            if value not in result:
                result.append(value)
        # Existing client uses this for TURN permission of a peer behind NAT.
        if len(result) < 4:
            result.append('seen='+ip)
        return result

    @staticmethod
    def peer(s, seat):
        side = 'join' if seat == 1 else 'host'
        raw = s[side+'_addrs']
        return {'name': s[side+'_name'] or 'Player', 'addrs': json.loads(raw)} if raw else None

    def match(self, db, op, body, headers, ip):
        s, seat = self.match_auth(db, headers)
        if seat > 2:
            w = db.execute('SELECT * FROM spectators WHERE session=? AND seat=? AND ended=0', (s['id'], seat)).fetchone()
            if op != 'watch' or body.get('v') != PROTOCOL or not w or not s['host_addrs'] or body.get('code') != s['code']:
                raise Refused('no room')
            db.execute('UPDATE spectators SET addrs=? WHERE session=? AND token=?',
                       (compact(self.addresses(body.get('addrs', []), ip)), s['id'], w['token']))
            return {'code': s['code'], 'key': w['key'], 'peer': self.peer(s, 2)}
        if op in ('host', 'join'):
            if body.get('v') != PROTOCOL:
                raise Refused('version')
            if (op == 'host') != (seat == 1):
                raise Refused('wrong seat')
            side = 'host' if seat == 1 else 'join'
            raw_name = body.get('name', 'Player')
            name = self.text(raw_name or 'Player', 19)
            # The existing compact parser does not decode JSON escapes.
            name = re.sub(r'[^A-Za-z0-9 _.-]', '', name) or 'Player'
            addrs = self.addresses(body.get('addrs', []), ip)
            if op == 'host':
                if not s['code']:
                    while True:
                        code = ''.join(secrets.choice('ABCDEFGHJKLMNPQRSTUVWXYZ23456789') for _ in range(6))
                        if not db.execute('SELECT 1 FROM sessions WHERE code=?', (code,)).fetchone():
                            break
                    db.execute('UPDATE sessions SET code=? WHERE id=?', (code, s['id']))
            elif not s['code'] or body.get('code') != s['code'] or not s['host_addrs']:
                raise Refused('no room')
            if side == 'join' and self.relay_only and not any(a.startswith('relay=') for a in json.loads(s['host_addrs'])):
                raise Refused('relay address not ready')
            # Repeat requests from the same authorized seat are idempotent.
            db.execute('UPDATE sessions SET %s_name=?,%s_addrs=?,%s_ip=? WHERE id=?' % (side, side, side),
                       (name, compact(addrs), ip, s['id']))
        else:
            expected = s['host_key'] if seat == 1 else s['join_key']
            if not s['code'] or body.get('code') != s['code'] or not hmac.compare_digest(body.get('key', ''), expected):
                raise Refused('no room')
            if op == 'addrs':
                if seat != 1:
                    raise Refused('wrong seat')
                db.execute('UPDATE sessions SET host_addrs=? WHERE id=?',
                           (compact(self.addresses(body.get('addrs'), ip)), s['id']))
            elif op not in ('poll', 'leave', 'relay'):
                raise Refused('bad request')
            # /v1/leave ends the temporary lookup, not the fixed room, seat,
            # allocation, or active game. Poll data remains until match ends.
        s = db.execute('SELECT * FROM sessions WHERE id=?', (s['id'],)).fetchone()
        out = {'code': s['code'] or '', 'key': s['host_key'] if seat == 1 else s['join_key'],
               'you': ip, 'peer': self.peer(s, seat)}
        if seat == 1:
            out['watchers'] = [json.loads(w['addrs']) for w in db.execute(
                'SELECT addrs FROM spectators WHERE session=? AND ended=0 AND addrs IS NOT NULL', (s['id'],))]
        if op in ('host', 'relay'):
            out.update(self.turn_login(s))
            out['relayOnly'] = self.relay_only
        return out

    def request(self, path, body, headers=None, ip='127.0.0.1'):
        headers = {k.lower(): v for k, v in (headers or {}).items()}
        if not isinstance(body, dict):
            return {'ok': False, 'error': 'JSON object required'}
        try:
            with self.db() as db:
                db.execute('BEGIN IMMEDIATE')
                self.clean(db)
                # Cleanup must commit even when the request belongs to an expired member.
                # Roll back only that refused operation, never restore the dead seats.
                db.execute('SAVEPOINT operation')
                try:
                    if path == '/lobby/v1/request':
                        out = self.lobby(db, body, headers)
                    elif re.fullmatch(r'/v1/(host|join|poll|addrs|leave|relay|watch)', path):
                        out = self.match(db, path[4:], body, headers, ip)
                    else:
                        raise Refused('unknown endpoint')
                except Refused as error:
                    db.execute('ROLLBACK TO operation')
                    out = {'ok': False, 'error': str(error)}
                finally:
                    db.execute('RELEASE operation')
            return {'ok': True, **out}
        except Refused as error:
            return {'ok': False, 'error': str(error)}


def load_config(path):
    config = json.loads(path.read_text('utf-8-sig'))
    database = Path(config.get('database', 'data/lobby.sqlite3'))
    if not database.is_absolute():
        database = path.parent / database
    config['database'] = str(database)
    secretfile = database.with_suffix('.secret')
    secretfile.parent.mkdir(parents=True, exist_ok=True)
    if not secretfile.exists():
        try:
            with secretfile.open('x', encoding='ascii') as f:
                f.write(secrets.token_hex(32))
            os.chmod(secretfile, 0o600)
        except FileExistsError:
            pass
    config['secret'] = secretfile.read_text('ascii').strip()
    config['access_key'] = os.environ.get('BT3_LOBBY_ACCESS_KEY', config.get('access_key', ''))
    config.setdefault('turn', {})['secret'] = os.environ.get('BT3_TURN_SECRET', config.get('turn', {}).get('secret', ''))
    return config


def make_handler(service):
    class Handler(BaseHTTPRequestHandler):
        server_version = 'BT3Lobby/2'
        def do_GET(self):
            if self.path == '/healthz':
                self.answer({'ok': True, 'api': 2, 'protocol': PROTOCOL, 'slots': SLOTS, 'edition': '0.16'})
            elif self.path in ('/updates/latest.json', '/updates/notes.txt') or re.fullmatch(
                    r'/updates/v[0-9]+(?:\.[0-9]+){1,3}/Tenkaichi3Decomp-windows-x64\.zip(?:\.sig)?', self.path):
                root = Path(service.config.get('updates_dir', Path(__file__).resolve().parents[1] / 'updates')).resolve()
                file = root / self.path[len('/updates/'):]
                if root not in file.resolve().parents or not file.is_file():
                    self.answer({'ok': False, 'error': 'No release published'}, 404)
                    return
                try:
                    with file.open('rb') as stream:
                        self.send_response(200)
                        self.send_header('Content-Type', 'application/zip' if file.suffix == '.zip' else 'application/json; charset=utf-8' if file.suffix == '.json' else 'text/plain; charset=utf-8')
                        self.send_header('Content-Length', str(os.fstat(stream.fileno()).st_size))
                        self.send_header('Cache-Control', 'no-store')
                        self.end_headers()
                        while data := stream.read(65536):
                            self.wfile.write(data)
                except (BrokenPipeError, ConnectionResetError, TimeoutError):
                    pass
            else:
                self.answer({'ok': False, 'error': 'POST /lobby/v1/request'}, 404)

        def do_POST(self):
            try:
                self.connection.settimeout(15)
                size = int(self.headers.get('Content-Length', '0'))
                if size < 2 or size > 8192:
                    self.answer({'ok': False, 'error': 'request too large'}, 413)
                    return
                body = json.loads(self.rfile.read(size).decode('utf-8'))
                ip = self.client_address[0]
                if service.config.get('trust_local_proxy') and ip in ('127.0.0.1', '::1'):
                    try:
                        ip = str(ipaddress.IPv4Address(self.headers.get('X-Real-IP', '')))
                    except ipaddress.AddressValueError:
                        self.answer({'ok': False, 'error': 'invalid proxy address'}, 400)
                        return
                out = service.request(self.path, body, dict(self.headers), ip)
                self.answer(out)
            except (ValueError, UnicodeError):
                self.answer({'ok': False, 'error': 'invalid JSON'}, 400)
            except (BrokenPipeError, ConnectionResetError, TimeoutError):
                pass
            except Exception:
                logging.exception('Lobby request failed')
                self.answer({'ok': False, 'error': '服务暂时不可用，请重试。'}, 503)

        def answer(self, out, status=200):
            raw = compact(out).encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(raw)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Connection', 'close')
            self.end_headers()
            self.wfile.write(raw)

        def log_message(self, *_):
            pass  # never log room tokens, access keys, player addresses or POST bodies
    return Handler


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', type=Path, default=Path(__file__).with_name('demo.json'))
    args = parser.parse_args()
    config = load_config(args.config.resolve())
    lobby = Lobby(config)
    from ping_service import PingService
    ping = PingService(lobby)
    ping.start()
    server = ThreadingHTTPServer((config.get('listen', '127.0.0.1'), config.get('port', 8787)), make_handler(lobby))
    server.daemon_threads = True
    print(f"BT3 lobby API 2 / battle protocol 6: http://{server.server_address[0]}:{server.server_address[1]}", flush=True)
    print('Permanent rooms: ' + ', '.join(r['name'] for r in config['rooms']), flush=True)
    print('Ctrl+C stops this service. No game resources are used.', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        ping.close()
        server.server_close()
