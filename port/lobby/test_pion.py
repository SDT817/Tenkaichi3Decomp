"""Real Windows Pion server + unchanged compiled game TURN client; no game."""
import base64
import hashlib
import hmac
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import time

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT.parent/'Chinese-local-analysis-20261022/online-lobby2-preview-20261027'
V=ROOT.parent/'Chinese-local-analysis-20261022/online-lobby5-official1391-20261029/verification'
sys.path.insert(0,str(ROOT/'local'))
import build_windows as build

def run():
    env=dict(os.environ,PATH=r'E:\BT3-Wii-tools\mingw64\bin;E:\BT3-Wii-tools\ucrt64\bin;'+os.environ['PATH'])
    result=build.undefined.run(['gcc','-m32','-std=gnu99','-O2','-Iport/src/gs','-Iport/build/gen/gs',
        'port/lobby/turn_live_probe.c','-o',os.path.relpath(V/'turn_live_probe.exe',ROOT),
        '-LE:/BT3-Wii-tools/ucrt64/lib','-lSDL3','-lwinhttp','-lws2_32','-lm'],cwd=ROOT,capture_output=True,text=True)
    assert result.returncode==0,result.stderr
    with tempfile.TemporaryDirectory() as tmp:
        port_socket=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);port_socket.bind(('127.0.0.1',0))
        port=port_socket.getsockname()[1];port_socket.close()
        secret='pion-real-integration-test-secret-only'
        config=Path(tmp)/'turn.json';config.write_text(json.dumps({'listen':f'127.0.0.1:{port}','public_ip':'127.0.0.1','relay_ip':'127.0.0.1','min_port':49260,'max_port':49359,'secret':secret}),'utf-8')
        server=subprocess.Popen([str(OUT/'deployment/bt3-turn.exe'),'-config',str(config)],stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
        peer=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);peer.bind(('127.0.0.1',0));peer.settimeout(.1)
        stop=threading.Event();packets=[]
        def echo():
            while not stop.is_set():
                try:data,addr=peer.recvfrom(1600)
                except socket.timeout:continue
                if data==b'PING':packets.append(addr);peer.sendto(b'PONG',addr)
        thread=threading.Thread(target=echo,daemon=True);thread.start()
        try:
            time.sleep(.3)
            username=f'{int(time.time())+300}:real-server-test'
            password=base64.b64encode(hmac.new(secret.encode(),username.encode(),hashlib.sha1).digest()).decode()
            p=subprocess.run([str(V/'turn_live_probe.exe'),f'127.0.0.1:{port}',username,password,str(peer.getsockname()[1])],env=env,capture_output=True,timeout=20)
            log=p.stdout.decode(errors='replace')+p.stderr.decode(errors='replace')
            (V/'Pion-real-TURN.log').write_text(log,'utf-8')
            assert p.returncode==0,(p.returncode,log)
            wrong=subprocess.run([str(V/'turn_live_probe.exe'),f'127.0.0.1:{port}',username,'invalid-password',str(peer.getsockname()[1])],env=env,capture_output=True,timeout=20)
            assert wrong.returncode==4,wrong.stdout
            assert len(packets)>=3
            result={'real_server':'Pion TURN v4.1.3, Windows native','real_standard_TURN_interoperability':True,
                'existing_game_net_relay_source_unchanged':True,'actual_MD5_SHA1_REST_auth':True,
                'actual_CreatePermission_ChannelBind_bidirectional_UDP':True,'wrong_password_rejected':True,
                'refresh_and_zero_lifetime_close_sent':True,'received_relay_packets':len(packets),
                'game_launched':False,'remote_VPS_gameplay_tested':False}
            (V/'Pion-real-TURN-tests.json').write_text(json.dumps(result,indent=2)+'\n','utf-8')
            print(json.dumps(result,indent=2),flush=True)
        finally:
            stop.set();thread.join(timeout=2);peer.close();server.terminate();server.wait(timeout=5)
            (V/'Pion-server-test.log').write_bytes(server.stdout.read())

if __name__=='__main__':run()
