"""Administrator persistence, permissions and idle/start transaction safety."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from directory_server import Directory
from server import Lobby, compact


class RoomSettingsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.key = '1'*64
        self.lobby_config = {'name':'Original','database':str(root/'rooms.db'),'secret':'test',
            'rooms':[{'id':'r0','name':'First'}, {'id':'r1','name':'Second','rules':{'rollback':4,'delay':2}}]}
        self.lobby = Lobby(self.lobby_config)
        self.directory_config = {'database':str(root/'directory.db'),'lobby_database':str(root/'rooms.db'),
            'lobby_server_id':'native','bootstrap_admin':{'id':'owner','name':'Owner',
                'key_hash':hashlib.sha256(self.key.encode()).hexdigest()},
            'initial_servers':[{'id':'native','name':'Original','url':'https://example.invalid'}]}
        self.directory = Directory(self.directory_config)

    def tearDown(self):
        self.temp.cleanup()

    def admin(self, op, key=None, **fields):
        return self.directory.request('/directory/v1/request',{'op':op,**fields},
            {'X-BT3-Lobby-Key':self.key if key is None else key})

    def save(self, room='r0', **rules):
        return self.admin('save_room',server='native',room=room,rules={'battle':1,'time':2,'speed':100,**rules})

    def call(self, op, **fields):
        if op == 'enter': fields.setdefault('sync_pause',1)
        return self.lobby.request('/lobby/v1/request',{'op':op,**fields})

    def test_default_100_persistence_and_preserved_hidden_rules(self):
        self.assertTrue(all(r['rules']['speed']==100 for r in self.call('list')['rooms']))
        self.assertTrue(self.save('r1',battle=4,time=0,speed=105)['ok'])
        expected = {'battle':4,'time':0,'speed':105,'rollback':4,'delay':2}
        self.assertEqual(self.call('list')['rooms'][1]['rules'],expected)
        self.lobby = Lobby(self.lobby_config)
        self.directory = Directory(self.directory_config)
        self.assertEqual(self.call('list')['rooms'][1]['rules'],expected)
        self.assertEqual(self.admin('whoami')['room_settings']['rooms'][1]['rules'],expected)
        self.assertEqual(self.call('list')['rooms'][0]['rules']['battle'],0)

    def test_add_rename_rules_and_restart(self):
        before = self.call('list')['rooms']
        self.assertTrue(self.admin('add_room',server='native',name='新房间')['ok'])
        new = next(r for r in self.call('list')['rooms'] if r['id'] not in {r['id'] for r in before})
        ident = new['id']
        self.assertEqual(new['rules']['speed'],100)
        self.assertTrue(self.save(ident,battle=4,time=1,speed=110)['ok'])
        self.assertTrue(self.admin('rename_room',server='native',room=ident,name='朋友的房间')['ok'])
        self.assertTrue(self.admin('rename_room',server='native',room='r0',name='原房间改名')['ok'])
        self.lobby = Lobby(self.lobby_config)
        self.directory = Directory(self.directory_config)
        listing = {r['id']:r for r in self.call('list')['rooms']}
        self.assertEqual(listing[ident]['name'],'朋友的房间')
        self.assertEqual(listing[ident]['rules'],{'battle':4,'time':1,'speed':110,'rollback':8,'delay':-2})
        self.assertEqual(listing['r0']['name'],'原房间改名')
        self.assertEqual(listing['r1']['name'],'Second')

    def test_room_metadata_auth_validation_and_limit(self):
        before = self.call('list')['rooms']
        for op,fields in [('add_room',{'name':'new'}),('rename_room',{'room':'r0','name':'renamed'})]:
            for key in ('','0'*64):
                self.assertFalse(self.admin(op,key,server='native',**fields)['ok'])
            self.assertFalse(self.admin(op,server='wrong',**fields)['ok'])
            for name in ('','a'*65,'   ','bad\nname',None):
                self.assertFalse(self.admin(op,server='native',**{**fields,'name':name})['ok'])
        self.assertEqual(self.call('list')['rooms'],before)
        for i in range(30):
            self.assertTrue(self.admin('add_room',server='native',name=str(i))['ok'])
        self.assertFalse(self.admin('add_room',server='native',name='too many')['ok'])
        self.lobby = Lobby(self.lobby_config)
        self.assertEqual(len(self.call('list')['rooms']),32)

    def test_rename_start_race_rejects_stale_epoch(self):
        a = self.call('enter',room='r0',name='A')['token']
        self.call('enter',room='r0',name='B')
        old = self.call('poll',token=a)['room']
        with ThreadPoolExecutor(2) as workers:
            start = workers.submit(self.call,'start',token=a,epoch=old['epoch'])
            rename = workers.submit(self.admin,'rename_room',server='native',room='r0',name='New')
            start,rename = start.result(),rename.result()
        self.assertNotEqual(start['ok'],rename['ok'])
        state = self.call('poll',token=a)['room']
        if start['ok']:
            self.assertEqual(state['name'],old['name'])
        else:
            self.assertEqual(state['name'],'New')
            self.assertFalse(self.call('start',token=a,epoch=old['epoch'])['ok'])

    def test_only_active_admin_can_change_rules(self):
        for key in ('','0'*64):
            self.assertFalse(self.admin('save_room',key,server='native',room='r0',rules={'battle':0,'time':0,'speed':100})['ok'])
        new = self.admin('add_admin',id='other',name='Other')['key']
        self.assertTrue(self.admin('save_room',new,server='native',room='r0',rules={'battle':0,'time':0,'speed':100})['ok'])
        self.assertTrue(self.admin('revoke_admin',id='other')['ok'])
        self.assertFalse(self.admin('save_room',new,server='native',room='r0',rules={'battle':0,'time':0,'speed':100})['ok'])
        public = compact(self.call('list'))+compact(self.admin('list',key=''))
        self.assertNotIn('key_hash',public)
        self.assertNotIn(self.key,public)

    def test_occupied_idle_room_updates_both_players_and_rejects_stale_start(self):
        a = self.call('enter',room='r0',name='A')['token']
        b = self.call('enter',room='r0',name='B')['token']
        old = self.call('poll',token=a)['room']['epoch']
        self.assertTrue(self.save(battle=3,time=1)['ok'])
        self.assertFalse(self.call('start',token=a,epoch=old)['ok'])
        for token in (a,b):
            state = self.call('poll',token=token)['room']
            self.assertEqual(state['rules']['speed'],100)
            self.assertEqual(state['rules']['battle'],3)
            self.assertNotEqual(state['epoch'],old)
        self.assertTrue(self.call('start',token=b,epoch=state['epoch'])['ok'])
        self.assertFalse(self.save()['ok'])
        state = self.call('poll',token=a)['room']
        self.call('launch',token=a,session=state['session'])
        self.assertFalse(self.save()['ok'])
        self.call('finish',token=a,session=state['session'])
        self.call('finish',token=b,session=state['session'])
        self.assertTrue(self.save()['ok'])

    def test_save_start_race_never_changes_active_session_rules(self):
        a = self.call('enter',room='r0',name='A')['token']
        self.call('enter',room='r0',name='B')
        old = self.call('poll',token=a)['room']
        with ThreadPoolExecutor(2) as workers:
            first = workers.submit(self.call,'start',token=a,epoch=old['epoch'])
            second = workers.submit(self.save,battle=4,time=0)
            start, save = first.result(), second.result()
        self.assertNotEqual(start['ok'],save['ok'])
        final = self.call('poll',token=a)['room']
        if start['ok']:
            self.assertEqual(final['rules'],old['rules'])
        else:
            self.assertEqual(final['phase'],'idle')
            self.assertEqual(final['rules']['battle'],4)

    def test_invalid_rules_and_wrong_server_leave_room_unchanged(self):
        before = self.call('list')['rooms']
        for field,values in {'battle':[-1,5,True,'1'], 'time':[-1,5,False,None], 'speed':[99,151,True,100.5]}.items():
            for value in values:
                self.assertFalse(self.save(**{field:value})['ok'],(field,value))
        for fields in ({'server':'wrong','room':'r0','rules':{'battle':0,'time':0,'speed':100}},
                       {'server':'native','room':'missing','rules':{'battle':0,'time':0,'speed':100}},
                       {'server':'native','room':'r0','rules':{'battle':0,'time':0,'speed':100,'delay':5}}):
            self.assertFalse(self.admin('save_room',**fields)['ok'])
        self.assertEqual(self.call('list')['rooms'],before)

    def test_server_rename_preserves_flags_and_survives_restart(self):
        self.admin('unpublish',id='native')
        self.assertTrue(self.admin('rename',id='native',url='https://example.invalid',name='新名称')['ok'])
        self.directory = Directory(self.directory_config)
        server = self.admin('whoami')['servers'][0]
        self.assertEqual(server['name'],'新名称')
        self.assertFalse(server['enabled'])
        self.assertFalse(server['locked'])
        self.assertFalse(self.admin('rename',id='native',url='https://wrong.invalid',name='Lost')['ok'])
        self.assertFalse(self.admin('rename',key='',id='native',url='https://example.invalid',name='Lost')['ok'])

    def test_deployment_migration_backs_up_without_replacing_database_identities(self):
        from deploy.migrate_lobby_settings import migrate
        root = Path(self.temp.name)
        config = root/'config'; config.mkdir()
        backup = root/'backup'; backup.mkdir()
        server = {**self.lobby_config, 'database':'../rooms.db','unrelated':{'keep':True}}
        directory = {**self.directory_config,'database':'../directory.db','unrelated':'preserve'}
        (config/'server.json').write_text(json.dumps(server),'utf-8')
        (config/'directory.json').write_text(json.dumps(directory),'utf-8')
        (config/'ip2626-deployment.json').write_text(json.dumps({'url':'https://custom.invalid'}),'utf-8')
        self.admin('publish',id='friends-main',name='Custom name',url='https://custom.invalid')
        with self.directory.db() as db: before = list(db.iterdump())
        migrate(root,backup)
        with self.directory.db() as db:self.assertEqual(list(db.iterdump()),before)
        with closing(sqlite3.connect(backup/'directory.sqlite3')) as db:self.assertEqual(list(db.iterdump()),before)
        updated = json.loads((config/'directory.json').read_text('utf-8'))
        self.assertEqual(updated['lobby_server_id'],'friends-main')
        self.assertEqual(updated['lobby_database'],str((root/'rooms.db').resolve()))
        self.assertEqual(updated['bootstrap_admin'],directory['bootstrap_admin'])
        self.assertEqual(updated['unrelated'],'preserve')
        updated = json.loads((config/'server.json').read_text('utf-8'))
        self.assertEqual(updated['unrelated'],server['unrelated'])
        self.assertTrue(all(r['rules']['speed']==100 for r in updated['rooms']))

    def migration_config(self, url='https://example.invalid'):
        root = Path(self.temp.name)
        config = root/'config'; config.mkdir()
        (config/'server.json').write_text(json.dumps(self.lobby_config),'utf-8')
        (config/'directory.json').write_text(json.dumps(self.directory_config),'utf-8')
        (config/'ip2626-deployment.json').write_text(json.dumps({'url':url}),'utf-8')
        backup = root/'backup'; backup.mkdir()
        return root,config,backup

    def test_migration_matches_actual_url_instead_of_fixed_id(self):
        from deploy.migrate_lobby_settings import migrate
        root,config,backup = self.migration_config('https://EXAMPLE.invalid:443/')
        self.admin('rename',id='native',url='https://example.invalid',name='Keep custom name')
        self.admin('unpublish',id='native')
        with self.directory.db() as db: before = list(db.iterdump())
        migrate(root,check=True)
        self.assertEqual(list(backup.iterdir()),[])
        migrate(root,backup)
        with self.directory.db() as db:self.assertEqual(list(db.iterdump()),before)
        updated = json.loads((config/'directory.json').read_text('utf-8'))
        self.assertEqual(updated['lobby_server_id'],'native')
        self.assertEqual(self.admin('whoami')['servers'][0]['name'],'Keep custom name')

    def test_migration_recovers_empty_directory_without_recreating_admins(self):
        from deploy.migrate_lobby_settings import migrate
        root,config,backup = self.migration_config()
        with self.directory.db() as db:
            db.execute('DELETE FROM servers')
            admins = [dict(r) for r in db.execute('SELECT * FROM admins ORDER BY id')]
        before = {p.name:p.read_bytes() for p in config.iterdir()}
        migrate(root,check=True)
        self.assertEqual({p.name:p.read_bytes() for p in config.iterdir()},before)
        self.assertEqual(self.admin('list')['servers'],[])
        migrate(root,backup)
        listing = self.admin('list')['servers']
        self.assertEqual(len(listing),1)
        self.assertEqual(listing[0]['url'],'https://example.invalid')
        self.assertEqual(listing[0]['name'],self.lobby_config['name'])
        ident = listing[0]['id']
        self.assertEqual(json.loads((config/'directory.json').read_text('utf-8'))['lobby_server_id'],ident)
        with self.directory.db() as db:
            self.assertEqual([dict(r) for r in db.execute('SELECT * FROM admins ORDER BY id')],admins)
        with closing(sqlite3.connect(backup/'directory.sqlite3')) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM servers').fetchone()[0],0)
        second = root/'second-backup'; second.mkdir()
        migrate(root,second)
        self.assertEqual(self.admin('list')['servers'],listing)

    def test_migration_never_replaces_another_servers_identifier(self):
        from deploy.migrate_lobby_settings import migrate
        root,config,backup = self.migration_config()
        self.admin('remove',id='native')
        self.admin('publish',id='native',name='Other server',url='https://other.invalid')
        old = self.admin('list')['servers'][0]
        migrate(root,backup)
        servers = self.admin('list')['servers']
        self.assertEqual(next(s for s in servers if s['id']=='native'),old)
        local = next(s for s in servers if s['url']=='https://example.invalid')
        self.assertNotEqual(local['id'],'native')
        self.assertEqual(json.loads((config/'directory.json').read_text('utf-8'))['lobby_server_id'],local['id'])

    def test_migration_ambiguous_endpoint_fails_before_config_changes(self):
        from deploy.migrate_lobby_settings import migrate
        root,config,backup = self.migration_config()
        self.admin('publish',id='duplicate',name='Duplicate',url='https://example.invalid:443/')
        before = {p.name:p.read_bytes() for p in config.iterdir()}
        with self.assertRaisesRegex(RuntimeError,'Multiple directory entries'):
            migrate(root,backup)
        self.assertEqual({p.name:p.read_bytes() for p in config.iterdir()},before)
        self.assertEqual(list(backup.iterdir()),[])


if __name__=='__main__':unittest.main(verbosity=2)
