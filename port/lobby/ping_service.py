"""Dolphin-style server-originated PING / client PONG RTT, outside battle UDP.

Dolphin reference: NetPlayServer.cpp:224-235,878-894 in the supplied 10912 tree.
No ENet dependency is needed for this small independent UDP measurement.
"""
import hashlib
import hmac
import secrets
import socket
import threading
import time

MAGIC = b'BT3PING2'


class PingService:
    def __init__(self, lobby):
        self.lobby = lobby
        self.stop = threading.Event()
        self.socket = None
        self.thread = None

    def start(self):
        config = self.lobby.config.get('ping', {})
        if 'port' not in config:
            return
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.bind((config.get('listen', '127.0.0.1'), config['port']))
        self.socket.settimeout(.1)
        # An ephemeral port is useful in tests, but must be advertised correctly.
        config['port'] = self.socket.getsockname()[1]
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def run(self):
        peers = {}
        keys = {}
        next_tick = 0
        while not self.stop.is_set():
            now = time.monotonic()
            if now >= next_tick:
                with self.lobby.db() as db:
                    members = db.execute('SELECT token FROM members WHERE expires>=?', (self.lobby.clock(),)).fetchall()
                keys = {hmac.new(self.lobby.secret, ('ping:'+r['token']).encode(), hashlib.sha256).hexdigest().encode(): r['token'] for r in members}
                peers = {k: p for k, p in peers.items() if k in keys and now-p['seen'] < 8}
                for key, peer in peers.items():
                    nonce = secrets.token_bytes(8)
                    peer.update(nonce=nonce, sent=now)
                    try:
                        self.socket.sendto(MAGIC+b'P'+nonce, peer['addr'])
                    except OSError:
                        pass  # A disconnected UDP endpoint must not stop other players' probes.
                next_tick = now+1
            try:
                packet, address = self.socket.recvfrom(256)
            except socket.timeout:
                continue
            except OSError:
                if self.stop.is_set():
                    return
                continue
            if len(packet) == 73 and packet.startswith(MAGIC+b'R'):
                key = packet[9:]
                if key in keys:
                    old = peers.get(key, {})
                    if old.get('addr') == address:
                        old['seen'] = now
                    else:
                        peers[key] = {'addr': address, 'seen': now, 'nonce': b'', 'sent': now}
                # Unauthenticated datagrams receive no response.
            elif len(packet) == 17 and packet.startswith(MAGIC+b'O'):
                for key, peer in peers.items():
                    if peer['addr'] == address and peer['nonce'] == packet[9:]:
                        rtt = max(0, min(10000, round((time.monotonic()-peer['sent'])*1000)))
                        peer['nonce'] = b''  # accept each response once
                        with self.lobby.db() as db:
                            db.execute('UPDATE members SET ping=?,ping_at=? WHERE token=?', (rtt, self.lobby.clock(), keys[key]))
                        break

    def close(self):
        self.stop.set()
        if self.thread:
            self.thread.join(timeout=2)
        if self.socket:
            self.socket.close()
