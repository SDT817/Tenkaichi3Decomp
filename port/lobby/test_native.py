"""Exercise the actual compiled WinHTTP and matching code, without launching a game."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import time
from http.server import ThreadingHTTPServer
from server import Lobby, make_handler
from directory_server import Directory
from ping_service import PingService
import hashlib

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT.parent/'Chinese-local-analysis-20261022/online-lobby2-preview-20261027/verification'
OUT.mkdir(parents=True,exist_ok=True)
BIN=OUT/'client_probe.exe'
env=dict(os.environ,PATH=r'E:\BT3-Wii-tools\mingw64\bin;E:\BT3-Wii-tools\ucrt64\bin;'+os.environ['PATH'])

def build():
    run=subprocess.run([r'E:\Phyton\python.exe','-X','utf8',str(Path(__file__).with_name('build_probes.py'))],cwd=ROOT,env=env,capture_output=True,text=True,encoding='utf-8',errors='replace')
    (OUT/'probe-build.log').write_text(run.stdout+run.stderr,'utf-8')
    assert run.returncode==0,run.stdout+run.stderr

def run():
    build()
    with tempfile.TemporaryDirectory() as tmp:
        config={'name':'Native HTTP 测试','database':str(Path(tmp)/'test.db'),'secret':'test-secret',
                'access_key':'native-key','ping':{'host':'127.0.0.1','port':0},'rooms':[{'id':'r0','name':'固定房间'}]}
        lobby=Lobby(config)
        ping=PingService(lobby);ping.start()
        server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(lobby))
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        url=f'http://127.0.0.1:{server.server_port}'
        processes=[]
        d=Directory({'database':str(Path(tmp)/'directory.db'), 'bootstrap_admin':{'id':'admin','name':'Native admin','key_hash':hashlib.sha256(b'1'*64).hexdigest()},
                     'initial_servers':[{'id':'native','name':'Native shared directory','url':url}]})
        directory=ThreadingHTTPServer(('127.0.0.1',0),make_handler(d))
        dt=threading.Thread(target=directory.serve_forever,daemon=True);dt.start()
        directory_url=f'http://127.0.0.1:{directory.server_port}'
        try:
            def call(op,**body):
                out=lobby.request('/lobby/v1/request',{'op':op,**body},{'X-BT3-Lobby-Key':'native-key'})
                assert out['ok'],out
                return out
            native=subprocess.run([str(BIN),'http',url+'/lobby/v1/request','{"op":"list"}','native-key'],env=env,capture_output=True,timeout=20)
            raw=native.stdout.decode('utf-8')
            assert native.returncode==0 and json.loads(raw)['rooms'][0]['name']=='固定房间',raw
            tokens=[]
            for seat in (2,1):
                t=call('enter',room='r0',name='Native'+str(seat))['token']
                call('seat',token=t,seat=seat);tokens.append(t)
            b,a=tokens
            epoch=call('poll',token=a)['room']['epoch']
            call('start',token=b,epoch=epoch)
            ar=call('poll',token=a)['room'];br=call('poll',token=b)['room']
            host=subprocess.Popen([str(BIN),'host',url,ar['match_token']],env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            processes.append(host)
            until=time.monotonic()+25
            code=''
            while time.monotonic()<until:
                code=call('poll',token=b)['room'].get('code','')
                if code:break
                time.sleep(.05)
            assert code,'Host did not publish hidden code'
            join=subprocess.Popen([str(BIN),'join',url,br['match_token'],code],env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            processes.append(join)
            jstdout,jstderr=join.communicate(timeout=45)
            hstdout,hstderr=host.communicate(timeout=45)
            for n,p,out,err in [('host',host,hstdout,hstderr),('join',join,jstdout,jstderr)]:
                text=out.decode('utf-8',errors='replace')+err.decode('utf-8',errors='replace')
                (OUT/f'native-{n}.log').write_text(text,'utf-8')
                assert p.returncode==0 and 'state=3' in text and 'transport_idle=1' in text,text
            result={'native_WinHTTP_UTF8_auth':True,'existing_Match_Begin_host_and_join':True,
                    'same_IP_two_clients':True,'private_task_config_snapshot':True,
                    'lookup_leave_preserves_fixed_room':call('poll',token=a)['room']['phase']=='starting',
                    'game_launched':False,'UDP_battle_gameplay':False}
            call('leave',token=a);call('leave',token=b)
            for seat in (2,1):
                cwd=Path(tmp)/('player'+str(seat));cwd.mkdir()
                p=subprocess.Popen([str(OUT/'lobby_probe.exe'),url,'native-key',str(seat),'unused',directory_url],
                                   cwd=cwd,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
                processes.append(p)
            failed=[]
            for seat,p in zip((2,1),processes[-2:]):
                out,err=p.communicate(timeout=90)
                text=out.decode('utf-8',errors='replace')+err.decode('utf-8',errors='replace')
                (OUT/f'headless-seat{seat}.log').write_text(text,'utf-8')
                if p.returncode:failed.append(text)
            assert not failed,'\n'.join(failed)
            result.update(headless_ImGui_UI_built=True, actual_lobby_Tick_two_sessions_per_seat=True,
                          session_hooks_simulated=True, real_game_handshake_tested=False,
                          directory_synced_on_two_fresh_clients=True, full_and_split_launch_options_checked=True, native_UDP_server_RTT_measured=True)
            (OUT/'native-tests.json').write_text(json.dumps(result,indent=2)+'\n','utf-8')
            print(json.dumps(result,indent=2),flush=True)
        finally:
            for p in processes:
                if p.poll() is None:p.terminate();p.wait(timeout=10)
            server.shutdown();server.server_close();thread.join()
            directory.shutdown();directory.server_close();dt.join()
            ping.close()

if __name__=='__main__':run()
