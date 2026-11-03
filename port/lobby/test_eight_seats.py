"""Control-plane transitions: eight seats, atomic swaps, spectators and upgrades."""
import json
from pathlib import Path
import tempfile
import threading
import unittest
from server import Lobby


class EightSeats(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.now = 1000.0
        self.config = {'database': str(Path(self.tmp.name)/'rooms.db'), 'secret': 'test-secret',
                       'rooms': [{'id': 'room', 'name': 'Permanent'}]}
        self.lobby = Lobby(self.config, lambda: self.now)
        self.tokens = [self.call('enter', room='room', name='P'+str(n))['token'] for n in range(1, 9)]

    def tearDown(self):
        self.tmp.cleanup()

    def call(self, op, index=None, **body):
        if op == 'enter': body.setdefault('sync_pause',1)
        if index is not None:
            body['token'] = self.tokens[index]
        result = self.lobby.request('/lobby/v1/request', {'op': op, **body})
        self.assertTrue(result['ok'], result)
        return result

    def test_seats_swaps_and_cooldown(self):
        self.assertEqual([s['seat'] for s in self.call('poll', 0)['room']['seats']], list(range(1, 9)))
        self.assertFalse(self.lobby.request('/lobby/v1/request', {'op':'enter','room':'room','name':'Ninth'})['ok'])
        self.assertEqual(self.call('swap', 0, seat=8)['room']['me'], 8)
        self.assertEqual(self.call('poll', 7)['room']['me'], 1)
        for i, target in [(0, 1), (7, 8), (2, 8)]:
            self.assertFalse(self.lobby.request('/lobby/v1/request', {'op':'swap','token':self.tokens[i],'seat':target})['ok'])
        self.now += 1
        self.assertEqual(self.call('swap', 0, seat=1)['room']['me'], 1)
        # Concurrent attempts cannot bypass the affected seats' cooldown.
        self.now += 1
        results = []
        def swap(index):
            results.append(self.lobby.request('/lobby/v1/request', {'op':'swap','token':self.tokens[index],'seat':8}))
        threads = [threading.Thread(target=swap, args=(n,)) for n in (0, 1)]
        for thread in threads: thread.start()
        for thread in threads: thread.join()
        self.assertEqual(sum(r['ok'] for r in results), 1)
        names = [s['name'] for s in self.call('poll', 0)['room']['seats']]
        self.assertEqual(len(set(names)), 8)

    def test_six_spectators_match_lifecycle(self):
        room = self.call('poll', 0)['room']
        self.assertTrue(room['can_start'])
        # Spectators' mode choices do not change the players' agreement.
        self.call('mode', 2, view='split')
        self.assertTrue(self.call('poll', 0)['room']['can_start'])
        self.assertFalse(self.lobby.request('/lobby/v1/request', {'op':'start','token':self.tokens[2],'epoch':room['epoch']})['ok'])
        self.call('start', 0, epoch=self.call('poll', 0)['room']['epoch'])
        session = self.call('poll', 0)['room']['session']
        def match(index, op, **fields):
            room = self.call('poll', index)['room']
            result = self.lobby.request('/v1/'+op, fields, {'X-BT3-Room':room['match_token']})
            self.assertTrue(result['ok'], result)
            return result
        host = match(0, 'host', v=6, addrs=['127.0.0.1:9001'], name='Host')
        match(1, 'join', v=6, code=host['code'], addrs=['127.0.0.1:9002'], name='Join')
        for n in range(2,8):
            watch = match(n, 'watch', v=6, code=host['code'], addrs=[f'127.0.0.1:{9001+n}'])
            self.assertEqual(watch['peer']['addrs'][0], '127.0.0.1:9001')
        poll = match(0,'poll',code=host['code'],key=host['key'])
        self.assertEqual(len(poll['watchers']),6)
        self.call('launch', 0, session=session)
        for n in range(2,8):
            self.call('launch', n, session=session)
            self.call('finish', n, session=session)
            self.assertEqual(self.call('poll', 0)['room']['phase'], 'playing')
        self.call('finish', 0, session=session)
        self.call('finish', 1, session=session)
        self.assertEqual(self.call('poll', 0)['room']['phase'], 'idle')

    def test_spectator_leaving_does_not_cancel_start(self):
        self.call('start',0,epoch=self.call('poll',0)['room']['epoch'])
        self.call('leave',7)
        self.assertEqual(self.call('poll',0)['room']['phase'],'starting')

    def test_upgrade_keeps_permanent_names_rules(self):
        with self.lobby.db() as db:
            db.execute("INSERT INTO room_names VALUES('room','Renamed',0)")
            db.execute("INSERT INTO room_names VALUES('extra','Extra',1)")
            db.execute("INSERT INTO room_rules VALUES('room',?)", (json.dumps({'battle':2,'speed':100}),))
        self.lobby = Lobby(self.config,lambda:self.now)
        rooms=self.call('list')['rooms']
        self.assertEqual(len(rooms),2)
        self.assertEqual(next(r for r in rooms if r['id']=='room')['name'],'Renamed')
        self.assertEqual(next(r for r in rooms if r['id']=='room')['rules']['battle'],2)


if __name__ == '__main__':
    unittest.main()
