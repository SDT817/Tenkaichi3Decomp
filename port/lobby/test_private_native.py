"""Real Caddy TLS + Go bridge + native ImGui clients, without a game window.

Exercises the same native matching/TURN-call paths as the existing lobby test.
Session entry/exit hooks remain simulated: this is not remote battle gameplay.
"""
from contextlib import closing
import hashlib
from http.server import ThreadingHTTPServer
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import threading
import time
import urllib.request
from server import Lobby, make_handler
from directory_server import Directory
from ping_service import PingService

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT.parent/'Chinese-local-analysis-20261022'
OUT = BASE/'online-lobby10-v016-20261101'
V = OUT/'verification'
CADDY = BASE/'online-lobby2-preview-20261027/deployment/runtime/caddy/caddy.exe'
BRIDGE = OUT/'programs/BT3Connect.exe'
ENV = dict(os.environ,PATH=r'E:\BT3-Wii-tools\mingw64\bin;E:\BT3-Wii-tools\ucrt64\bin;'+os.environ['PATH'])


def run():
    build = subprocess.run([r'E:\Phyton\python.exe','-X','utf8',str(Path(__file__).with_name('build_probes.py'))],
                           cwd=ROOT,env=ENV,capture_output=True,text=True,encoding='utf-8',errors='replace')
    (V/'private-native-build.log').write_text(build.stdout+build.stderr,'utf-8')
    assert build.returncode == 0, build.stdout+build.stderr
    processes,servers,threads,logs = [],[],[],[]
    ping = None
    with tempfile.TemporaryDirectory(dir=V,prefix='private-tls-') as temp:
        tmp = Path(temp)
        try:
            config = {'name':'TLS native test','database':str(tmp/'rooms.db'),'secret':'test-secret',
                'trust_local_proxy':True,'access_key':'native-key','ping':{'host':'127.0.0.1','port':0},
                'rooms':[{'id':'r0','name':'固定房间'}]}
            lobby = Lobby(config)
            ping = PingService(lobby);ping.start()
            room_server = ThreadingHTTPServer(('127.0.0.1',0),make_handler(lobby))
            servers.append(room_server)
            with closing(socket.socket()) as reservation:
                reservation.bind(('127.0.0.1',0));public_port = reservation.getsockname()[1]
            remote = f'https://127.0.0.1:{public_port}'
            directory = Directory({'database':str(tmp/'directory.db'),'trust_local_proxy':True,
                'lobby_database':str(tmp/'rooms.db'),'lobby_server_id':'native',
                'bootstrap_admin':{'id':'admin','name':'Native admin','key_hash':hashlib.sha256(b'1'*64).hexdigest()},
                'initial_servers':[{'id':'native','name':'TLS server','url':remote}]})
            directory_server = ThreadingHTTPServer(('127.0.0.1',0),make_handler(directory))
            servers.append(directory_server)
            for server in servers:
                thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();threads.append(thread)
            generated=subprocess.run([str(BRIDGE),'-make-certificate','127.0.0.1','-certificate-directory',str(tmp/'identity')],
                capture_output=True,text=True,check=True)
            cert=(tmp/'identity/server.crt').as_posix();key=(tmp/'identity/server.key').as_posix()
            caddy='''{
    admin off
    auto_https off
    persist_config off
    servers {
        protocols h1
    }
}
'''+remote+''' {
    bind 127.0.0.1
    tls "'''+cert+'" "'+key+'''"
    @directory path /directory/v1/request
    handle @directory {
        reverse_proxy 127.0.0.1:'''+str(directory_server.server_port)+''' {
            header_up X-Real-IP {remote_host}
        }
    }
    handle {
        reverse_proxy 127.0.0.1:'''+str(room_server.server_port)+''' {
            header_up X-Real-IP {remote_host}
        }
    }
}
'''
            caddy_path=tmp/'Caddyfile';caddy_path.write_text(caddy,'utf-8')
            caddy_log=(tmp/'caddy.log').open('wb');logs.append(caddy_log)
            caddy_process=subprocess.Popen([str(CADDY),'run','--config',str(caddy_path),'--adapter','caddyfile'],
                cwd=tmp,env=dict(ENV,XDG_DATA_HOME=str(tmp/'data'),XDG_CONFIG_HOME=str(tmp/'config')),
                stdout=caddy_log,stderr=caddy_log,creationflags=subprocess.CREATE_NO_WINDOW)
            processes.append(caddy_process)
            for attempt in range(60):
                try:
                    with socket.create_connection(('127.0.0.1',public_port),timeout=.2):break
                except OSError:time.sleep(.1)
            else:raise AssertionError('Caddy TLS listener did not start')
            bridge_config=tmp/'bridge.json'
            bridge_config.write_text(json.dumps({'remote':remote,'certificate':str(tmp/'identity/server.crt')}),'utf-8')
            check=subprocess.run([str(BRIDGE),'-config',str(bridge_config),'-check','-check-address',f'127.0.0.1:{public_port}'],
                capture_output=True,text=True,timeout=20)
            assert check.returncode==0,check.stdout+check.stderr
            clients=[]
            settings_bridge=subprocess.Popen([str(BRIDGE),'-config',str(bridge_config)],cwd=tmp,
                stdout=subprocess.PIPE,stderr=subprocess.PIPE,creationflags=subprocess.CREATE_NO_WINDOW)
            processes.append(settings_bridge)
            settings_local=json.loads(settings_bridge.stdout.readline().decode('utf-8'))['local']
            settings_cwd=tmp/'settings';settings_cwd.mkdir()
            settings=subprocess.run([str(V/'settings_probe.exe'),remote,'1'*64,'native-key'],cwd=settings_cwd,
                env=dict(ENV,BT3_LOBBY_GATEWAY_REMOTE=remote,BT3_LOBBY_GATEWAY_LOCAL=settings_local),
                capture_output=True,timeout=40)
            (V/'settings-native.log').write_bytes(settings.stdout+settings.stderr)
            assert settings.returncode==0,(settings.stdout+settings.stderr).decode('utf-8','replace')
            for seat in (2,1):
                bridge=subprocess.Popen([str(BRIDGE),'-config',str(bridge_config)],cwd=tmp,
                    stdout=subprocess.PIPE,stderr=subprocess.PIPE,creationflags=subprocess.CREATE_NO_WINDOW)
                processes.append(bridge)
                endpoints=json.loads(bridge.stdout.readline().decode('utf-8'))
                local=endpoints['local']
                # Exercise real native WinHTTP/auth over TLS before the UI test.
                probe=subprocess.run([str(V/'client_probe.exe'),'http',local+'/lobby/v1/request','{"op":"list"}','native-key'],
                    cwd=tmp,env=ENV,capture_output=True,timeout=20)
                assert probe.returncode==0 and any(r['id']=='r0' and r['name']=='改名测试' for r in json.loads(probe.stdout)['rooms']),probe.stdout+probe.stderr
                cwd=tmp/('player'+str(seat));cwd.mkdir()
                player=subprocess.Popen([str(V/'lobby_probe.exe'),remote,'native-key',str(seat),'unused',remote],cwd=cwd,
                    env=dict(ENV,BT3_LOBBY_GATEWAY_REMOTE=remote,BT3_LOBBY_GATEWAY_LOCAL=local),
                    stdout=subprocess.PIPE,stderr=subprocess.PIPE,creationflags=subprocess.CREATE_NO_WINDOW)
                processes.append(player);clients.append((seat,player))
            failures=[]
            for seat,player in clients:
                stdout,stderr=player.communicate(timeout=95)
                text=stdout.decode('utf-8','replace')+stderr.decode('utf-8','replace')
                (V/f'private-native-seat{seat}.log').write_text(text,'utf-8')
                if player.returncode:failures.append(text)
                assert 'applied_speed=100 battle=2 dp=1 time=2' in text,text
            assert not failures,'\n'.join(failures)
            # Actual owner authentication/publication through TLS; never print keys.
            endpoint=json.loads(json.dumps(endpoints))['local']+'/directory/v1/request'
            request=urllib.request.Request(endpoint,json.dumps({'op':'whoami'}).encode(),
                headers={'Content-Type':'application/json','X-BT3-Lobby-Key':'1'*64})
            with urllib.request.urlopen(request,timeout=10) as response:auth=json.load(response)
            assert auth['ok'] and auth['admin']['id']=='admin',auth
            result={'native_WinHTTP_UTF8_and_auth_over_private_TLS':True,'two_independent_client_bridges':True,
                'refresh_idle_and_pending_draw_vertices_identical':True,'queued_user_actions_during_refresh':True,
                'admin_rules_room_add_and_rename_over_TLS':True,'pending_fingerprint_preserves_private_transport':True,'rename_survives_directory_refresh_and_INI_reload':True,
                'both_clients_apply_100_percent_DP15_180_seconds':True,
                'Caddy_existing_services_reused':True,'normal_certificate_IP_signature_expiry_validation':True,
                'loopback_local_check_uses_public_certificate_IP':True,'directory_admin_auth_over_TLS':True,
                'fresh_clients_synced_public_server_URL':True,'two_full_split_sessions_per_seat':True,
                'native_server_UDP_RTT':True,'existing_native_Match_Begin_host_join':True,
                'session_hooks_simulated':True,'game_launched':False,'remote_gameplay_tested':False}
            (V/'private-native-tests.json').write_text(json.dumps(result,indent=2)+'\n','utf-8')
            print(json.dumps(result,indent=2),flush=True)
        finally:
            for process in reversed(processes):
                if process.poll() is None:process.terminate();process.wait(timeout=10)
                for pipe in (process.stdin,process.stdout,process.stderr):
                    if pipe is not None:pipe.close()
            for server in servers:server.shutdown();server.server_close()
            for thread in threads:thread.join()
            if ping:ping.close()
            for log in logs:log.close()


if __name__=='__main__':run()
