"""Two players and six real spectator readiness handshakes via forced TURN."""
from pathlib import Path
import os
import subprocess
import sys
import json
import tempfile
import threading
import socket
import time
from http.server import ThreadingHTTPServer
from server import Lobby,make_handler
ROOT=Path(__file__).resolve().parents[2]
BASE=ROOT.parent/'Chinese-local-analysis-20261022'
OUT=BASE/'online-lobby8-v014-20261030/verification'
sys.path.insert(0,str(ROOT/'local'))
import build_windows as b

def run():
    cmd=['gcc','-m32','-std=gnu99','-O2','-ffunction-sections','-fdata-sections','-Wl,--gc-sections',
         '-Iport/src/gs','-Iport/build/gen/gs','port/lobby/spec_wire_probe.c',
         *['port/src/gs/'+n+'.c' for n in ['net_match','net_relay','net_sign','net_lobby','net_chat']],
         '-o',os.path.relpath(OUT/'spec_wire_probe.exe',ROOT),'-LE:/BT3-Wii-tools/ucrt64/lib','-lSDL3','-lwinhttp','-lws2_32','-lm']
    r=b.undefined.run(cmd,cwd=ROOT,capture_output=True,text=True)
    assert r.returncode==0,r.stderr
    env=dict(os.environ,BT3_RELAY_ONLY='1',PATH=r'E:\BT3-Wii-tools\mingw64\bin;E:\BT3-Wii-tools\ucrt64\bin;'+os.environ['PATH'])
    with tempfile.TemporaryDirectory(dir=OUT,prefix='spectator-') as directory:
        tmp=Path(directory)
        with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
        secret='six-spectator-test-secret-at-least-32-characters'
        config=tmp/'turn.json';config.write_text(json.dumps({'listen':f'127.0.0.1:{port}','public_ip':'127.0.0.1',
            'relay_ip':'127.0.0.1','min_port':49460,'max_port':49559,'secret':secret}),'utf-8')
        turn=subprocess.Popen([str(BASE/'online-lobby2-preview-20261027/deployment/bt3-turn.exe'),'-config',str(config)],
                              stdout=subprocess.PIPE,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
        lobby=Lobby({'database':str(tmp/'db'),'secret':'test','rooms':[{'id':'r','name':'r'}],
                     'turn':{'required':True,'server':f'127.0.0.1:{port}','secret':secret}})
        server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(lobby))
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        processes=[]
        def call(op,token=None,**fields):
            if op == 'enter': fields.setdefault('sync_pause',1)
            out=lobby.request('/lobby/v1/request',{'op':op,**({'token':token} if token else {}),**fields})
            assert out['ok'],out
            return out
        try:
            tokens=[call('enter',room='r',name='P'+str(n))['token'] for n in range(8)]
            call('start',tokens[0],epoch=call('poll',tokens[0])['room']['epoch'])
            def spawn(index,role,code=''):
                room=call('poll',tokens[index])['room']
                p=subprocess.Popen([str(OUT/'spec_wire_probe.exe'),role,f'http://127.0.0.1:{server.server_port}',room['match_token'],code],
                                   env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,creationflags=subprocess.CREATE_NO_WINDOW)
                processes.append(p)
            spawn(0,'host')
            end=time.monotonic()+20
            while time.monotonic()<end:
                if processes[0].poll() is not None:
                    raise AssertionError(processes[0].communicate())
                code=call('poll',tokens[1])['room']['code']
                if code:break
                time.sleep(.05)
            assert code
            spawn(1,'join',code)
            for n in range(2,8):spawn(n,'watch',code)
            for n,p in enumerate(processes):
                stdout,stderr=p.communicate(timeout=50)
                text=(stdout+stderr).decode('utf-8','replace')
                (OUT/f'spectator-seat{n+1}.log').write_text(text,'utf-8')
                assert p.returncode==0,text
                if n==0:assert 'six_authorized_fingerprint_validated_spectators=6' in text,text
                if n>1:assert 'watch=1 relay=1' in text,text
            report={'real_native_net_c_spectator_ready':6,'forced_TURN':True,'spectator_fingerprints_validated_by_host':True,
                    'battle_protocol':6,'host_session_ready_flag_stubbed':True,'battle_replay_not_run':True}
            (OUT/'spectator-wire-tests.json').write_text(json.dumps(report,indent=2)+'\n','utf-8')
            print(json.dumps(report,indent=2))
        finally:
            for p in processes:
                if p.poll() is None:p.terminate();p.wait(timeout=5)
            server.shutdown();server.server_close();thread.join()
            turn.terminate();turn.wait(timeout=5);turn.stdout.close()

if __name__=='__main__':run()
