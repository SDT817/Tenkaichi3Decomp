"""Actual Windows GUI launcher + pinned TLS repair before starting a fake child."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import hashlib
import json
import os
import shutil
import socket
import ssl
import subprocess
import tempfile
import threading
from publish_update import publish, FILES, ASSET

ROOT=Path(__file__).resolve().parents[2]
BASE=ROOT.parent/'Chinese-local-analysis-20261022'
OUT=BASE/'online-lobby11-v017-20261103'
KEY=BASE/'online-lobby7-v013-20261030/private-signing/update_signing_key.txt'

def run():
    report={}
    with tempfile.TemporaryDirectory(dir=OUT/'verification',prefix='integrity-tls-') as directory:
        tmp=Path(directory); canonical=tmp/'canonical'; canonical.mkdir()
        for name in FILES:shutil.copy2(OUT/'programs'/name,canonical/name)
        shutil.copy2(OUT/'verification/desktop_child.exe',canonical/'Tenkaichi3Decomp.exe')
        (canonical/'fonts').mkdir();(canonical/'fonts/test.ttf').write_bytes(b'fixture-font')
        downloads=0
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                nonlocal downloads
                if self.path=='/healthz':raw=b'{"ok":true,"protocol":6}'
                elif self.path=='/updates/v0.17/'+ASSET:
                    downloads+=1;raw=(tmp/'updates/v0.17'/ASSET).read_bytes()
                elif self.path=='/updates/v0.17/'+ASSET+'.sig':raw=(tmp/'updates/v0.17'/(ASSET+'.sig')).read_bytes()
                else:self.send_error(404);return
                self.send_response(200);self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
            def log_message(self,*args):pass
        subprocess.run([str(OUT/'programs/BT3Connect.exe'),'-make-certificate','127.0.0.1',
            '-certificate-directory',str(tmp/'identity')],capture_output=True,check=True)
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);context.load_cert_chain(tmp/'identity/server.crt',tmp/'identity/server.key')
        server.socket=context.wrap_socket(server.socket,server_side=True)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        remote=f'https://127.0.0.1:{server.server_port}'
        publish(canonical,tmp/'updates','0.17','Local fixture, never deployed',KEY,remote)
        try:
            for case in ('damaged_files','damaged_launcher','missing_manifest','offline_good'):
                game=tmp/case/'中文目录 with spaces';game.parent.mkdir();shutil.copytree(canonical,game)
                shutil.copy2(tmp/'identity/server.crt',game/'bt3_server.crt')
                (game/'bt3_gateway.json').write_text(json.dumps({'remote':remote,'certificate':'bt3_server.crt'}),'utf-8')
                preserved={'bt3_settings.txt':b'personal-settings','bt3_directory_admin.ini':b'personal-admin',
                           'wii_profiles/mine.ini':b'personal-bindings','fonts/fonts.tsv':b'personal-font-list',
                           'saves/card.ps2':b'save','gamedata/disc/SLUS_216.78':b'ISO-NOT-MANAGED'}
                for name,data in preserved.items():
                    p=game/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
                if case=='damaged_files':
                    (game/'SDL3.dll').unlink();(game/'fonts/test.ttf').write_bytes(b'wrong');(game/'Tenkaichi3Decomp.dat').write_bytes(b'bad')
                elif case=='damaged_launcher':(game/'启动游戏.exe').write_bytes(b'broken-launcher')
                elif case=='missing_manifest':(game/'bt3_files.json').unlink()
                before=downloads
                if case in ('damaged_launcher','offline_good'):
                    # Invoke the standalone fallback even if the GUI EXE cannot start.
                    checked=subprocess.run([str(game/'BT3Connect.exe'),'-config',str(game/'bt3_gateway.json'),'-repair'],
                        cwd=OUT,capture_output=True,timeout=40,creationflags=subprocess.CREATE_NO_WINDOW)
                    assert checked.returncode==0,(case,checked.stdout,checked.stderr)
                checked=subprocess.run([str(game/'启动游戏.exe')],cwd=OUT,timeout=40,creationflags=subprocess.CREATE_NO_WINDOW)
                log=(game/'bt3-launcher.log').read_text('utf-8')
                (OUT/'verification'/('integrity-launcher-'+case+'.log')).write_text(log,'utf-8')
                assert checked.returncode==0,(case,log)
                assert downloads-before==(0 if case=='offline_good' else 1),(case,downloads-before)
                for p in canonical.rglob('*'):
                    if p.is_file():assert (game/p.relative_to(canonical)).read_bytes()==p.read_bytes(),(case,p)
                for name,data in preserved.items():assert (game/name).read_bytes()==data,(case,name)
                value=json.loads((game/'desktop-child.json').read_text('utf-8'))
                assert Path(value['cwd']).resolve()==game.resolve() and value['health']['ok'],value
                host,port=value['local'].removeprefix('http://').split(':')
                try:
                    with socket.create_connection((host,int(port)),timeout=.2):raise AssertionError('bridge left running')
                except (ConnectionRefusedError,TimeoutError):pass
                report[case]=True
        finally:server.shutdown();server.server_close();thread.join()
    report.update(real_GUI_launcher=True,real_pinned_TLS=True,real_child_environment=True,
                  correct_files_not_downloaded=True,game_assets_and_personal_settings_preserved=True,
                  actual_game_or_remote_server_started=False)
    (OUT/'verification/integrity-launcher.json').write_text(json.dumps(report,indent=2)+'\n','utf-8')
    print(json.dumps(report,indent=2))

if __name__=='__main__':run()
