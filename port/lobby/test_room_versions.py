"""Only lobby admission changes; battle packets/rollback are untouched."""
from pathlib import Path
from contextlib import closing
import sqlite3
import tempfile
import unittest
from server import Lobby


class RoomVersions(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.config = {'database':str(Path(self.temp.name)/'db.sqlite3'), 'secret':'fixture',
                       'rooms':[{'id':'r','name':'Room'}]}
        self.lobby = Lobby(self.config)

    def tearDown(self): self.temp.cleanup()

    def request(self, op, **body):
        return self.lobby.request('/lobby/v1/request', {'op':op, **body})

    def call(self, op, **body):
        r = self.request(op, **body)
        self.assertTrue(r['ok'], r)
        return r

    def enter(self, version='0.15', **body):
        return self.call('enter', room='r', name='Player', sync_pause=1, version=version, **body)['token']

    def room(self, token): return self.call('poll', token=token)['room']

    def start(self, token):
        return self.request('start', token=token, epoch=self.room(token)['epoch'])

    def test_same_version_can_start_and_versions_are_public(self):
        a,b = self.enter(),self.enter()
        room = self.room(a)
        self.assertTrue(room['can_start'])
        self.assertTrue(room['versions_match'])
        self.assertEqual([s['version'] for s in room['seats'][:2]], ['0.15','0.15'])
        self.assertTrue(self.start(b)['ok'])

    def test_different_versions_disable_and_server_refuses_start(self):
        a,b = self.enter(),self.enter('0.16')
        for token in (a,b):
            self.assertFalse(self.room(token)['can_start'])
            self.assertFalse(self.room(token)['versions_match'])
            response = self.start(token)
            self.assertFalse(response['ok'])
            self.assertIn('版本不同',response['error'])
            self.assertIn('更新',response['error'])

    def test_old_released_clients_infer_versions_and_no_false_match(self):
        a = self.enter()
        old = self.call('enter',room='r',name='Old',sync_pause=1)['token']
        self.assertEqual(self.room(a)['seats'][1]['version'],'0.14')
        self.assertFalse(self.start(a)['ok'])
        self.call('leave',token=old)
        old = self.call('enter',room='r',name='Old')['token']
        self.assertEqual(self.room(a)['seats'][1]['version'],'0.13')
        self.assertFalse(self.room(a)['clients_current'])
        self.assertFalse(self.start(a)['ok'])

    def test_spectators_checked_vacant_seats_ignored_and_leave_recovers(self):
        a,b = self.enter(),self.enter()
        spectator = self.enter('0.14')
        self.assertFalse(self.room(a)['can_start'])
        self.call('seat',token=spectator,seat=0)
        self.assertTrue(self.room(a)['can_start'])
        self.call('seat',token=spectator,seat=8)
        self.assertFalse(self.start(a)['ok'])
        self.call('leave',token=spectator)
        self.assertTrue(self.room(a)['can_start'])
        self.assertTrue(self.start(a)['ok'])

    def test_numeric_versions_and_missing_components(self):
        a,b = self.enter('0.15.0'),self.enter('0.15.0.0')
        self.assertTrue(self.room(a)['versions_match'])
        self.assertTrue(self.start(a)['ok'])
        self.assertGreater(Lobby.version_key('0.15.10'),Lobby.version_key('0.15.9'))

    def test_invalid_versions_do_not_create_members(self):
        for version in [None,True,15,'','dev','0.15\n','0.15-rc1','0.15.1.2.3','0.1000000000']:
            r = self.request('enter',room='r',name='Invalid',sync_pause=1,version=version)
            self.assertFalse(r['ok'],version)
        self.assertFalse(any(s['name'] for s in self.call('list')['rooms'][0]['seats']))

    def test_old_014_schema_is_migrated_in_place(self):
        # Simulate the column-absent 0.14 database with persistent room preferences.
        with closing(sqlite3.connect(self.config['database'])) as db:
            with db:
                db.execute('ALTER TABLE members DROP COLUMN version')
                db.execute("UPDATE rooms SET allow_pause=0 WHERE id='r'")
        self.lobby = Lobby(self.config)
        a,b = self.enter(),self.enter()
        room = self.room(a)
        self.assertEqual(room['allow_pause'],0)
        self.assertTrue(room['can_start'])


if __name__ == '__main__': unittest.main()
