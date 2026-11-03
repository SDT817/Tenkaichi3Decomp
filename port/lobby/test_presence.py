"""Hard exits, rejected requests, partial launches and lost Finish recovery."""
from pathlib import Path
import tempfile
import unittest
from server import Lobby, LEASE, FINISH_TIMEOUT, START_TIMEOUT, digest

class Presence(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.now=1800000000.0
        self.service=Lobby({'database':str(Path(self.tmp.name)/'rooms.db'),'secret':'fixture',
            'rooms':[{'id':'r','name':'Permanent'}]},lambda:self.now)
        self.a=self.call('enter',room='r',seat=1,name='A')['token']
        self.b=self.call('enter',room='r',seat=2,name='B')['token']

    def tearDown(self):self.tmp.cleanup()
    def raw(self,op,token=None,**fields):
        return self.service.request('/lobby/v1/request',{'op':op,**fields,**({'token':token} if token else {})})
    def call(self,op,token=None,**fields):
        if op=='enter':fields.update(sync_pause=1,version='0.16')
        result=self.raw(op,token,**fields);self.assertTrue(result['ok'],result);return result
    def room(self):return self.call('list')['rooms'][0]
    def begin(self,both=True):
        room=self.call('start',self.a,epoch=self.room()['epoch'])['room']
        session=room['session'];self.call('launch',self.a,session=session)
        if both:self.call('launch',self.b,session=session)
        return session
    def advance(self,seconds,tokens):
        while seconds>0:
            step=min(5,seconds);self.now+=step;seconds-=step
            for token in tokens:self.call('poll',token)

    def test_idle_hard_exit_releases_seat_and_epoch(self):
        epoch=self.room()['epoch'];self.advance(LEASE+1,[self.b])
        room=self.room();self.assertEqual(room['phase'],'idle')
        self.assertEqual(room['seats'][0]['name'],'');self.assertFalse(room['can_start'])
        self.assertNotEqual(room['epoch'],epoch)
        c=self.call('enter',room='r',name='Replacement')['token']
        self.assertEqual(self.call('poll',c)['room']['me'],1)
        self.assertTrue(self.call('poll',c)['room']['can_start'])

    def test_expired_request_does_not_rollback_cleanup(self):
        self.now+=LEASE
        self.assertFalse(self.raw('poll',self.a)['ok'])
        with self.service.db() as db:self.assertEqual(db.execute('SELECT count(*) FROM members').fetchone()[0],0)
        self.assertTrue(all(not s['name'] for s in self.room()['seats']))

    def test_refused_operation_still_rolls_back_its_own_mutations(self):
        with self.service.db() as db:
            before=dict(db.execute('SELECT * FROM members WHERE token=?',(digest(self.a),)).fetchone())
        self.now+=1
        self.assertFalse(self.raw('seat',self.a,seat=2)['ok'])
        with self.service.db() as db:
            self.assertEqual(before,dict(db.execute('SELECT * FROM members WHERE token=?',(digest(self.a),)).fetchone()))

    def test_playing_normal_exit_resets_immediately(self):
        self.begin();self.call('leave',self.a)
        room=self.call('poll',self.b)['room'];self.assertEqual(room['phase'],'idle')
        self.assertEqual(room['session'],'');self.assertEqual(room['seats'][0]['name'],'')
        self.call('enter',room='r',name='Replacement')

    def test_playing_hard_exit_does_not_wait_for_peer_finish(self):
        self.begin();self.advance(LEASE+1,[self.b])
        room=self.room();self.assertEqual(room['phase'],'idle')
        self.assertEqual(room['seats'][0]['name'],'');self.call('enter',room='r',name='New')

    def test_preexisting_single_player_playing_room_is_repaired(self):
        self.begin()
        with self.service.db() as db:db.execute('DELETE FROM members WHERE token=?',(digest(self.a),))
        self.assertEqual(self.room()['phase'],'idle')
        self.call('enter',room='r',name='New')

    def test_room_with_missing_session_is_repaired(self):
        session=self.begin()
        with self.service.db() as db:db.execute('DELETE FROM sessions WHERE id=?',(session,))
        self.assertEqual(self.room()['phase'],'idle')

    def test_partial_launch_with_live_heartbeats_times_out(self):
        self.begin(both=False)
        self.advance(START_TIMEOUT+1,[self.a,self.b]);self.assertEqual(self.room()['phase'],'idle')

    def test_full_live_match_is_not_reset_by_start_timeout(self):
        self.begin();self.advance(START_TIMEOUT+LEASE+10,[self.a,self.b])
        self.assertEqual(self.room()['phase'],'playing')

    def test_one_finish_with_other_live_client_eventually_unlocks(self):
        session=self.begin();self.call('finish',self.a,session=session)
        self.assertEqual(self.room()['phase'],'playing')
        self.advance(FINISH_TIMEOUT+1,[self.a,self.b]);self.assertEqual(self.room()['phase'],'idle')

    def test_spectator_exit_or_expiry_never_stops_live_match(self):
        c=self.call('enter',room='r',seat=3,name='Spectator')['token']
        session=self.begin();self.advance(LEASE+1,[self.a,self.b])
        self.assertEqual(self.room()['phase'],'playing')
        self.assertEqual(self.room()['seats'][2]['name'],'')
        self.assertFalse(self.raw('finish',c,session=session)['ok'])
        self.assertEqual(self.room()['phase'],'playing')

    def test_late_finish_cannot_reset_replacement_match(self):
        old=self.begin();self.call('leave',self.a)
        c=self.call('enter',room='r',name='Replacement')['token']
        room=self.call('start',self.b,epoch=self.room()['epoch'])['room'];new=room['session']
        self.assertNotEqual(old,new)
        self.call('finish',self.b,session=old)
        self.assertEqual(self.room()['session'],new)
        self.call('launch',self.b,session=new);self.call('launch',c,session=new)
        self.assertEqual(self.room()['phase'],'playing')

    def test_both_exit_and_next_entry_clean_without_polls(self):
        self.begin();self.now+=LEASE+1
        c=self.call('enter',room='r',name='New')['token']
        room=self.call('poll',c)['room'];self.assertEqual(room['me'],1)
        self.assertEqual(room['phase'],'idle');self.assertFalse(room['seats'][1]['name'])

if __name__=='__main__':unittest.main()
