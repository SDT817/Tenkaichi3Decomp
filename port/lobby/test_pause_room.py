"""The pause policy is one immutable server-agreed session option."""
from pathlib import Path
import tempfile
import unittest
from server import Lobby

class PauseRoom(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.config={'database':str(Path(self.temp.name)/'db.sqlite3'),'secret':'test',
                     'rooms':[{'id':'r','name':'Existing'}]}
        self.lobby=Lobby(self.config)
        self.a=self.call('enter',room='r',name='A',sync_pause=1)['token']
        self.b=self.call('enter',room='r',name='B',sync_pause=1)['token']
    def tearDown(self):self.temp.cleanup()
    def raw(self,op,**body):return self.lobby.request('/lobby/v1/request',{'op':op,**body})
    def call(self,op,**body):
        value=self.raw(op,**body);self.assertTrue(value['ok'],value);return value
    def room(self,token):return self.call('poll',token=token)['room']
    def start(self):return self.call('start',token=self.a,epoch=self.room(self.a)['epoch'])
    def test_default_toggle_shared_and_restart_persistence(self):
        self.assertEqual(self.room(self.a)['allow_pause'],1)
        epoch=self.room(self.a)['epoch']
        self.call('pause',token=self.b,allow=0)
        self.assertEqual(self.room(self.a)['allow_pause'],0)
        self.assertNotEqual(self.room(self.a)['epoch'],epoch)
        self.lobby=Lobby(self.config)
        self.assertEqual(self.call('list')['rooms'][0]['allow_pause'],0)
    def test_session_snapshot_and_no_edit_during_connection(self):
        spectator=self.call('enter',room='r',name='C',sync_pause=1)['token']
        self.call('pause',token=self.a,allow=0);self.start()
        for token in [self.a,self.b,spectator]:
            self.assertEqual(self.room(token)['match_pause'],0)
            self.assertFalse(self.raw('pause',token=token,allow=1)['ok'])
        self.assertEqual(self.room(self.a)['match_pause'],0)
    def test_default_yes_shared_with_spectators(self):
        spectator=self.call('enter',room='r',name='C',sync_pause=1)['token']
        self.start()
        self.assertEqual([self.room(t)['match_pause'] for t in [self.a,self.b,spectator]],[1,1,1])
    def test_only_players_can_change_and_input_is_strict(self):
        spectator=self.call('enter',room='r',name='C',sync_pause=1)['token']
        self.assertFalse(self.raw('pause',token=spectator,allow=0)['ok'])
        for value in [True,False,-1,2,None,'0']:
            self.assertFalse(self.raw('pause',token=self.a,allow=value)['ok'])
        self.assertEqual(self.room(self.a)['allow_pause'],1)
    def test_old_clients_or_spectators_cannot_start_different_simulations(self):
        old=self.call('enter',room='r',name='Old')['token']
        self.assertFalse(self.room(self.a)['can_start'])
        self.assertFalse(self.raw('start',token=self.a,epoch=self.room(self.a)['epoch'])['ok'])
        self.call('pause',token=self.a,allow=0)
        self.assertFalse(self.raw('start',token=self.a,epoch=self.room(self.a)['epoch'])['ok'])
        self.call('leave',token=old)
        self.assertTrue(self.room(self.a)['can_start'])
        self.start()
    def test_stale_start_after_policy_change_rejected(self):
        epoch=self.room(self.a)['epoch']
        self.call('pause',token=self.b,allow=0)
        self.assertFalse(self.raw('start',token=self.a,epoch=epoch)['ok'])

if __name__=='__main__':unittest.main()
