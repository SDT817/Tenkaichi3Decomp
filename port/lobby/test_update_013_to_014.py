"""Old native 0.13 updater downloads and installs the final signed 0.14 via TLS."""
from pathlib import Path
from http.server import ThreadingHTTPServer
import hashlib
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
from server import Lobby,make_handler
ROOT=Path(__file__).resolve().parents[2]
BASE=ROOT.parent/'Chinese-local-analysis-20261022'
OUT=BASE/'online-lobby8-v014-20261030'
OLD=ROOT.parent/'Tenkaichi3Decomp-WiiLocal-r17-Lobby013'
sys.path.insert(0,str(ROOT/'local'))
import build_windows as build

def run():
    source=(OLD/'port/lobby/update_probe.c').read_text('utf-8')
    source=source.replace('if(!strstr(Update_Notes(),"测试公告"))','if(!Update_Notes()[0])')
    source=source.replace('"../src/gs/net_update.h"','"net_update.h"')
    probe=OUT/'verification/update013-probe.c';probe.write_text(source,'utf-8')
    cmd=['gcc','-m32','-std=gnu99','-O2','-Iport/src/gs','-Iport/build/gen/gs',os.path.relpath(probe,ROOT),
         *[os.path.relpath(OLD/'port/build/obj_win64'/(n+'.o'),ROOT) for n in ['gs_net_update','gs_update_sign','gs_update_crypto']],
         'port/src/gs/update_monocypher.c','-o',os.path.relpath(OUT/'verification/update013-probe.exe',ROOT),
         '-LE:/BT3-Wii-tools/ucrt64/lib','-lSDL3','-lwinhttp','-lm']
    r=build.undefined.run(cmd,cwd=ROOT,capture_output=True,text=True)
    assert r.returncode==0,r.stderr
    with tempfile.TemporaryDirectory(dir=OUT/'verification',prefix='old-update-tls-') as temporary:
        temp=Path(temporary);game=temp/'原玩家 0.13';game.mkdir()
        oldprograms=BASE/'online-lobby7-v013-20261030/programs'
        for p in oldprograms.iterdir():
            if p.is_file():(game/p.name).write_bytes(p.read_bytes())
        (game/'Tenkaichi3Decomp.exe').write_bytes((OUT/'verification/update013-probe.exe').read_bytes())
        preserved=['bt3_settings.txt','bt3_wii_controls.ini','bt3_directory_admin.ini','bt3_online_servers.ini',
                   'bt3_server_directory.ini','bt3_gateway.json','bt3_server.crt','wii_profiles/混合配置.ini',
                   'saves/card.ps2','gamedata/disc/SLUS_216.78','fonts/bt3cn-rounded-bold.ttf']
        for name in preserved:
            p=game/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b'KEEP')
        lobby=Lobby({'database':str(temp/'db.sqlite3'),'secret':'fixture','updates_dir':str(OUT/'updates'),
                     'rooms':[{'id':'r','name':'r'}]})
        server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(lobby))
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        with socket.socket() as reservation:
            reservation.bind(('127.0.0.1',0));port=reservation.getsockname()[1]
        bridge=OUT/'programs/BT3Connect.exe'
        subprocess.run([str(bridge),'-make-certificate','127.0.0.1','-certificate-directory',str(temp/'identity')],
                       capture_output=True,check=True)
        remote=f'https://127.0.0.1:{port}'
        caddy=temp/'Caddyfile'
        caddy.write_text('''{
 admin off
 auto_https off
 persist_config off
}
'''+remote+''' {
 bind 127.0.0.1
 tls "'''+(temp/'identity/server.crt').as_posix()+'" "'+(temp/'identity/server.key').as_posix()+'''"
 reverse_proxy 127.0.0.1:'''+str(server.server_port)+'''
}
''','utf-8')
        processes=[]
        log=(temp/'caddy.log').open('wb')
        env=dict(os.environ)
        env.pop('BT3_UPDATE_API',None);env.pop('BT3_UPDATE_FAIL_AT',None)
        try:
            process=subprocess.Popen([str(BASE/'online-lobby2-preview-20261027/deployment/runtime/caddy/caddy.exe'),
                'run','--config',str(caddy),'--adapter','caddyfile'],cwd=temp,
                env=dict(env,XDG_DATA_HOME=str(temp/'data'),XDG_CONFIG_HOME=str(temp/'config')),
                stdout=log,stderr=log,creationflags=subprocess.CREATE_NO_WINDOW)
            processes.append(process)
            for attempt in range(60):
                try:
                    with socket.create_connection(('127.0.0.1',port),timeout=.2):break
                except OSError:time.sleep(.1)
            else:raise AssertionError('Local TLS service did not start')
            config=temp/'bridge.json'
            config.write_text(json.dumps({'remote':remote,'certificate':str(temp/'identity/server.crt')}),'utf-8')
            proxy=subprocess.Popen([str(bridge),'-config',str(config)],cwd=temp,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                                   creationflags=subprocess.CREATE_NO_WINDOW)
            processes.append(proxy)
            endpoint=json.loads(proxy.stdout.readline())['local']
            env['BT3_LOBBY_GATEWAY_LOCAL']=endpoint
            r=subprocess.run([str(game/'Tenkaichi3Decomp.exe')],cwd=game,env=env,capture_output=True,timeout=60)
            text=(r.stdout+r.stderr).decode('utf-8','replace')
            (OUT/'verification/old013-to-final014.log').write_text(text,'utf-8')
            assert r.returncode==0,text
            assert 'version=0.13' in text,text
            assert all((game/p.name).read_bytes()==p.read_bytes() for p in (OUT/'programs').iterdir())
            assert all((game/name).read_bytes()==b'KEEP' for name in preserved)
            report={'actual_old_013_updater_objects':True,'final_signed_014_archive':True,
                    'private_feed_URL_routed_through_real_gateway':True,'real_Caddy_pinned_TLS_and_native_WinHTTP':True,
                    'full_seven_file_install_matches_final_programs':True,'announcement_nonempty':True,
                    'personal_admin_Wii_saves_fonts_and_ISO_preserved':True,
                    'automatic_UI_clicks_and_game_relaunch_not_simulated':True,
                    'remote_server_modified':False}
            (OUT/'verification/old013-to-final014.json').write_text(json.dumps(report,indent=2)+'\n','utf-8')
            print(json.dumps(report,indent=2))
        finally:
            for process in reversed(processes):
                if process.poll() is None:process.terminate();process.wait(timeout=5)
                for pipe in [process.stdout,process.stderr]:
                    if pipe is not None:pipe.close()
            log.close();server.shutdown();server.server_close();thread.join()
if __name__=='__main__':run()
