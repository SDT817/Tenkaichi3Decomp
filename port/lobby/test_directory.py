import hashlib, json
from pathlib import Path
import tempfile, threading, unittest, urllib.request
from http.server import ThreadingHTTPServer
from directory_server import Directory, valid_url
from server import compact, make_handler


class DirectoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.key='1'*64
        self.config={'database':str(Path(self.tmp.name)/'directory.db'),
                     'bootstrap_admin':{'id':'admin','name':'Admin','key_hash':hashlib.sha256(self.key.encode()).hexdigest()},
                     'initial_servers':[{'id':'local','name':'本机演示大厅','url':'http://127.0.0.1:8787'}]}
        self.d=Directory(self.config)
    def tearDown(self):self.tmp.cleanup()
    def call(self,op,key=None,**body):return self.d.request('/directory/v1/request',{'op':op,**body},{'X-BT3-Lobby-Key':key or ''})
    def test_public_cannot_administer_and_no_credentials_leak(self):
        public=self.call('list');self.assertTrue(public['ok']);self.assertEqual(len(public['servers']),1)
        self.assertNotIn('key_hash',compact(public));self.assertNotIn(self.key,compact(public))
        for op in ('whoami','publish','remove','add_admin','revoke_admin'):
            self.assertFalse(self.call(op)['ok'])
    def test_admin_publish_update_disable_delete_persists(self):
        p=self.call('publish',self.key,id='new',name='好友服',url='https://example.invalid',locked=True)
        self.assertTrue(p['ok']);self.assertEqual(len(self.call('list')['servers']),2)
        self.assertTrue(self.call('unpublish',self.key,id='new')['ok']);self.assertEqual(len(self.call('list')['servers']),1)
        self.assertEqual(len(self.call('whoami',self.key)['servers']),2)
        self.assertTrue(self.call('remove',self.key,id='local')['ok'])
        self.d=Directory(self.config);self.assertEqual(self.call('list')['servers'],[])
    def test_multiple_admins_revocation_and_self_protection(self):
        new=self.call('add_admin',self.key,id='friend',name='另一位管理员');self.assertTrue(new['ok'])
        other=new['key'];self.assertTrue(self.call('whoami',other)['ok'])
        self.assertFalse(self.call('revoke_admin',self.key,id='admin')['ok'])
        self.assertTrue(self.call('publish',other,id='a',name='A',url='https://a.invalid')['ok'])
        self.assertTrue(self.call('revoke_admin',self.key,id='friend')['ok'])
        self.assertFalse(self.call('whoami',other)['ok'])
        with self.d.db() as db:self.assertNotIn(other,str([dict(r) for r in db.execute('SELECT * FROM admins')]))
    def test_invalid_urls_and_duplicate_identifiers(self):
        for u in ('http://evil.example','https://user:pass@example.com','https://x/#secret','http://172.evil.example','https://x:bad','https://x\nX: y'):
            self.assertFalse(valid_url(u),u)
        self.assertTrue(valid_url('https://friends.example'));self.assertTrue(valid_url('http://192.168.1.2:8787'))
        self.assertFalse(self.call('publish',self.key,id='../bad',name='A',url='https://x.invalid')['ok'])
        self.assertFalse(self.call('add_admin',self.key,id='admin',name='duplicate')['ok'])
    def test_real_http_fresh_clients_observe_shared_updates(self):
        s=ThreadingHTTPServer(('127.0.0.1',0),make_handler(self.d));t=threading.Thread(target=s.serve_forever,daemon=True);t.start()
        try:
            def fresh_client():
                req=urllib.request.Request(f'http://127.0.0.1:{s.server_port}/directory/v1/request',b'{"op":"list"}',headers={'Content-Type':'application/json'})
                with urllib.request.urlopen(req,timeout=5) as r:return json.load(r)
            self.assertEqual(len(fresh_client()['servers']),1)
            self.call('publish',self.key,id='two',name='第二台',url='https://second.invalid')
            self.assertEqual(len(fresh_client()['servers']),2)
            self.assertEqual(len(fresh_client()['servers']),2)
        finally:s.shutdown();s.server_close();t.join()


if __name__=='__main__':unittest.main(verbosity=2)
