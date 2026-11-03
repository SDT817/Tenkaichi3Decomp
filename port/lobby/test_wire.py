"""Two actual official v6 UDP/fingerprint handshakes through a local Pion relay.

No battle/session implementation or assets are loaded. Game-only hooks abort if
accidentally reached. This verifies the real connection, not a simulated poll.
"""
from http.server import ThreadingHTTPServer
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import threading
import time
from server import Lobby, make_handler

ROOT=Path(__file__).resolve().parents[2]
BASE=ROOT.parent/'Chinese-local-analysis-20261022'
OUT=BASE/'online-lobby8-v014-20261030/verification'
ENV=dict(os.environ,PATH=r'E:\BT3-Wii-tools\mingw64\bin;E:\BT3-Wii-tools\ucrt64\bin;'+os.environ['PATH'],BT3_RELAY_ONLY='1')

def run():
    with tempfile.TemporaryDirectory(dir=OUT,prefix='wire-') as directory:
        tmp=Path(directory)
        with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as s:
            s.bind(('127.0.0.1',0));port=s.getsockname()[1]
        turn_config=tmp/'turn.json'
        turn_config.write_text(json.dumps({'listen':f'127.0.0.1:{port}','public_ip':'127.0.0.1',
            'relay_ip':'127.0.0.1','min_port':49360,'max_port':49459,'secret':'wire-test-secret-at-least-32-characters'}),'utf-8')
        turn=subprocess.Popen([str(BASE/'online-lobby2-preview-20261027/deployment/bt3-turn.exe'),'-config',str(turn_config)],
            stdout=subprocess.PIPE,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
        lobby=Lobby({'database':str(tmp/'rooms.db'),'secret':'wire-only','rooms':[{'id':'wire','name':'wire'}],
            'turn':{'required':True,'server':f'127.0.0.1:{port}','secret':'wire-test-secret-at-least-32-characters'}})
        server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(lobby))
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        clients=[]
        try:
            def call(op,**fields):
                if op == 'enter': fields.setdefault('sync_pause',1)
                answer=lobby.request('/lobby/v1/request',{'op':op,**fields})
                assert answer['ok'],answer
                return answer
            a=call('enter',room='wire',name='A')['token']
            b=call('enter',room='wire',name='B')['token']
            call('start',token=a,epoch=call('poll',token=a)['room']['epoch'])
            host_room=call('poll',token=a)['room']
            url=f'http://127.0.0.1:{server.server_port}'
            host=subprocess.Popen([str(OUT/'wire_probe.exe'),'host',url,host_room['match_token']],
                stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=ENV,creationflags=subprocess.CREATE_NO_WINDOW)
            clients.append(host)
            until=time.monotonic()+25
            while time.monotonic()<until:
                joined=call('poll',token=b)['room']
                if joined['code']:break
                if host.poll() is not None:raise AssertionError(host.communicate())
                time.sleep(.05)
            else:raise AssertionError('Host code did not arrive through the required relay')
            join=subprocess.Popen([str(OUT/'wire_probe.exe'),'join',url,joined['match_token'],joined['code']],
                stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=ENV,creationflags=subprocess.CREATE_NO_WINDOW)
            clients.append(join)
            for name,client in zip(('host','join'),clients):
                stdout,stderr=client.communicate(timeout=50)
                text=(stdout+stderr).decode('utf-8','replace')
                (OUT/('wire-'+name+'.log')).write_text(text,'utf-8')
                assert client.returncode==0,text
                assert 'state=2 fingerprint_heard=1 data_bad=0 relay=1' in text,text
            report={'actual_net_c_StartCode_Poll_and_UDP_handshake':True,'official_protocol':6,
                'both_peers_received_and_validated_fingerprint':True,'forced_relay_on_both_sides':True,
                'actual_native_match_and_relay_code':True,'real_local_Pion_server':True,
                'fingerprint_data_stubbed':True,'battle_session_never_started':True,'remote_gameplay_tested':False}
            (OUT/'wire-tests.json').write_text(json.dumps(report,indent=2)+'\n','utf-8')
            print(json.dumps(report,indent=2))
        finally:
            for client in clients:
                if client.poll() is None:client.terminate();client.wait(timeout=5)
                for pipe in (client.stdout,client.stderr):pipe.close()
            server.shutdown();server.server_close();thread.join()
            turn.terminate();turn.wait(timeout=5)
            (OUT/'wire-turn.log').write_bytes(turn.stdout.read());turn.stdout.close()

if __name__=='__main__':run()
