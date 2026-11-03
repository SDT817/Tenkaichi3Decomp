"""Room transactions, single-click start, mode agreement and match authorization."""
from concurrent.futures import ThreadPoolExecutor
import base64, copy, hashlib, hmac, json
from pathlib import Path
import tempfile, threading, unittest, urllib.request
from http.server import ThreadingHTTPServer
from server import Lobby, compact, make_handler


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.now = 1800000000
        self.config = {'name':'测试大厅','database':str(Path(self.temp.name)/'lobby.db'),
                       'secret':'test-secret-only','access_key':'friends',
                       'rooms':[{'id':f'r{i}','name':f'常驻房 {i}'} for i in range(3)]}
        self.service = Lobby(self.config, clock=lambda:self.now)
        self.headers = {'X-BT3-Lobby-Key':'friends'}

    def tearDown(self): self.temp.cleanup()
    def raw(self, op, token=None, **body):
        if op == 'enter': body.setdefault('sync_pause',1)
        return self.service.request('/lobby/v1/request',{'op':op,**({'token':token} if token else {}),**body},self.headers)
    def call(self, op, token=None, **body):
        out=self.raw(op,token,**body); self.assertTrue(out['ok'],out); return out
    def enter(self, name='玩家甲', room='r0', seat=None):
        t=self.call('enter',room=room,name=name)['token']
        if seat is not None: self.call('seat',t,seat=seat)
        return t
    def start(self, room='r0'):
        b=self.enter('PlayerB',room,2);a=self.enter('PlayerA',room,1)
        self.call('start',b,epoch=self.call('poll',b)['room']['epoch'])
        ar=self.call('poll',a)['room'];br=self.call('poll',b)['room']
        self.assertEqual(ar['session'],br['session']); self.assertNotEqual(ar['match_token'],br['match_token'])
        self.assertEqual((ar['me'],br['me']),(1,2));return a,b,ar,br
    def match(self, op, room, **body):
        out=self.service.request('/v1/'+op,body,{'X-BT3-Room':room['match_token']},'203.0.113.17')
        self.assertTrue(out['ok'],out);return out

    def test_protocol5_rejected_and_protocol6_accepted(self):
        a,b,ar,br=self.start()
        refused=self.service.request('/v1/host',{'v':5,'name':'A','addrs':['127.0.0.1:7000']},
            {'X-BT3-Room':ar['match_token']},'127.0.0.1')
        self.assertFalse(refused['ok'])
        self.assertTrue(self.match('host',ar,v=6,name='A',addrs=['127.0.0.1:7000'])['ok'])

    def test_auto_seats_ready_without_auto_start(self):
        a=self.enter();one=self.call('poll',a)['room']
        self.assertEqual(one['me'],1);self.assertTrue(one['ready']);self.assertEqual(one['view'],'full')
        self.assertFalse(one['can_start']);self.assertFalse(self.raw('start',a,epoch=one['epoch'])['ok'])
        b=self.enter('玩家乙');two=self.call('poll',b)['room']
        self.assertEqual(two['me'],2);self.assertTrue(two['can_start']);self.assertEqual(two['phase'],'idle')
        self.assertEqual(two['session'],'');self.assertTrue(self.raw('enter',name='第三人',room='r0')['ok'])

    def test_atomic_concurrent_entry_and_start(self):
        with ThreadPoolExecutor(12) as pool:
            entered=[r for r in pool.map(lambda n:self.raw('enter',room='r0',name=f'P{n}'),range(12)) if r['ok']]
        self.assertEqual(len(entered),8);a,b=[r['token'] for r in sorted(entered,key=lambda r:r['room']['me'])[:2]]
        epoch=self.call('poll',a)['room']['epoch']
        with ThreadPoolExecutor(2) as pool:
            starts=list(pool.map(lambda t:self.raw('start',t,epoch=epoch),[a,b]))
        self.assertEqual(sum(r['ok'] for r in starts),1)
        with self.service.db() as db:self.assertEqual(db.execute('SELECT count(*) FROM sessions').fetchone()[0],1)

    def test_mode_mismatch_stale_start_and_frozen_session(self):
        a=self.enter('甲');b=self.enter('乙');old=self.call('poll',a)['room']['epoch']
        view=self.call('mode',a,view='split')['room']
        self.assertFalse(view['mode_match']);self.assertFalse(view['can_start'])
        self.assertFalse(self.raw('start',b,epoch=view['epoch'])['ok'])
        self.call('mode',b,view='split');self.assertFalse(self.raw('start',a,epoch=old)['ok'])
        view=self.call('poll',a)['room'];self.assertTrue(view['can_start'])
        started=self.call('start',a,epoch=view['epoch'])['room'];self.assertEqual(started['match_view'],'split')
        self.assertFalse(self.raw('mode',b,view='full')['ok']);self.call('cancel',b,session=started['session'])
        again=self.call('poll',a)['room'];self.assertTrue(again['ready']);self.assertEqual(again['phase'],'idle')
        self.assertEqual(again['view'],'split')

    def test_seat_release_and_reentry(self):
        a=self.enter();b=self.enter('乙');self.assertFalse(self.raw('seat',b,seat=1)['ok'])
        self.call('seat',a,seat=0);self.assertFalse(self.call('poll',b)['room']['can_start'])
        self.assertFalse(self.raw('start',a,epoch=self.call('poll',a)['room']['epoch'])['ok'])
        self.call('seat',a,seat=1);self.assertTrue(self.call('poll',a)['room']['can_start'])

    def test_restart_clears_presence_not_rooms(self):
        a,b,ar,br=self.start();self.service=Lobby(self.config,clock=lambda:self.now)
        rooms=self.call('list')['rooms'];self.assertEqual(len(rooms),3)
        self.assertTrue(all(r['phase']=='idle' and not any(s['name'] for s in r['seats']) for r in rooms))
        self.assertFalse(self.raw('poll',a)['ok'])
        self.assertFalse(self.service.request('/v1/host',{'v':6},{'X-BT3-Room':ar['match_token']})['ok'])

    def test_hidden_pairing_no_cross_room_lookup_leave(self):
        a,b,ar,br=self.start();a2,b2,ar2,br2=self.start('r1')
        host=self.match('host',ar,v=6,name='A',addrs=['192.168.1.2:7000'])
        self.assertEqual(host['code'],self.match('host',ar,v=6,name='A',addrs=['192.168.1.2:7000'])['code'])
        self.assertEqual(self.call('poll',b)['room']['code'],host['code']);self.assertEqual(self.call('poll',b2)['room']['code'],'')
        bad=self.service.request('/v1/join',{'v':6,'code':host['code'],'name':'B','addrs':['192.168.1.3:7001']},{'X-BT3-Room':br2['match_token']})
        self.assertFalse(bad['ok'])
        joined=self.match('join',br,v=6,code=host['code'],name='B',addrs=['192.168.1.3:7001'])
        self.assertEqual(joined['peer']['name'],'A');self.assertIn('seen=203.0.113.17',joined['peer']['addrs'])
        self.match('leave',ar,code=host['code'],key=host['key']);self.match('poll',br,code=host['code'],key=joined['key'])
        self.assertEqual(self.call('poll',a)['room']['phase'],'starting')

    def test_late_messages_and_four_repeated_matches(self):
        a,b,ar,br=self.start();old=ar['session'];self.call('cancel',a,session=old)
        for _ in range(4):
            room=self.call('poll',a)['room'];current=self.call('start',b,epoch=room['epoch'])['room']['session']
            self.assertNotEqual(current,old);self.call('cancel',a,session=old)
            self.assertEqual(self.call('poll',b)['room']['session'],current)
            self.call('launch',a,session=current);self.call('finish',a,session=current)
            self.assertEqual(self.call('poll',b)['room']['phase'],'playing');self.call('finish',b,session=current)
            view=self.call('poll',a)['room'];self.assertEqual(view['phase'],'idle');self.assertTrue(all(s['ready'] for s in view['seats'] if s['name']))
            old=current

    def test_expiry_and_timeout(self):
        a,b,ar,br=self.start()
        # Maintain both real heartbeats while testing the independent start timeout.
        for _ in range(19):
            self.now+=5;self.call('poll',a);self.call('poll',b)
        self.assertEqual(self.call('poll',a)['room']['phase'],'idle')
        for _ in range(6):
            self.now+=5;self.call('poll',a)
        self.assertEqual(self.call('poll',a)['room']['seats'][1]['name'],'')

    def test_required_turn_gate_and_rest_credentials(self):
        config=copy.deepcopy(self.config);config['turn']={'required':True,'server':'203.0.113.9:3478','secret':'turn-test'}
        self.service=Lobby(config,clock=lambda:self.now);a,b,ar,br=self.start()
        host=self.match('host',ar,v=6,name='A',addrs=['192.168.1.2:7000']);self.assertEqual(self.call('poll',b)['room']['code'],'')
        login=host['turn'];expected=base64.b64encode(hmac.new(b'turn-test',login['username'].encode(),hashlib.sha1).digest()).decode()
        self.assertEqual(expected,login['credential'])
        self.match('addrs',ar,code=host['code'],key=host['key'],addrs=['192.168.1.2:7000','relay=203.0.113.9:50002'])
        self.assertEqual(self.call('poll',b)['room']['code'],host['code'])
        self.assertIn('relay=203.0.113.9:50002',self.match('join',br,v=6,code=host['code'],name='B',addrs=['10.0.0.1:8000'])['peer']['addrs'])

    def test_access_and_invalid_mode(self):
        self.assertFalse(self.service.request('/lobby/v1/request',{'op':'list'})['ok']);a=self.enter()
        for mode in ('invalid',None,1,True):self.assertFalse(self.raw('mode',a,view=mode)['ok'])
        self.assertFalse(self.raw('ready',a,ready=True)['ok']);self.assertFalse(self.raw('poll','0'*48)['ok'])

    def test_real_http_unicode_and_version(self):
        s=ThreadingHTTPServer(('127.0.0.1',0),make_handler(self.service));t=threading.Thread(target=s.serve_forever,daemon=True);t.start()
        try:
            req=urllib.request.Request(f'http://127.0.0.1:{s.server_port}/lobby/v1/request',compact({'op':'list'}).encode(),headers={'Content-Type':'application/json',**self.headers})
            with urllib.request.urlopen(req,timeout=5) as r:out=json.load(r)
            self.assertEqual(out['api'],2);self.assertEqual(out['protocol'],6);self.assertEqual(out['rooms'][0]['name'],'常驻房 0')
        finally:s.shutdown();s.server_close();t.join()


if __name__=='__main__':unittest.main(verbosity=2)
