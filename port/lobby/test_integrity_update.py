"""Actual C updater: retries, per-file readback, rollback and personal files."""
import base64
import hashlib
from http.server import ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import zipfile
from server import Lobby,make_handler
from publish_update import key,ASSET

ROOT=Path(__file__).resolve().parents[2]
BASE=ROOT.parent/'Chinese-local-analysis-20261022'
OUT=BASE/'online-lobby11-v017-20261103'
sys.path.insert(0,str(ROOT/'local'))
import build_windows as build

def run():
    command=['gcc','-m32','-std=gnu99','-O2','-Iport/src/gs','-Iport/build/gen/gs','port/lobby/integrity_update_probe.c',
        *[os.path.relpath(build.undefined.OBJ/(n+'.o'),ROOT) for n in ['gs_net_update','gs_update_sign','gs_update_crypto']],
        'port/src/gs/update_monocypher.c','-Wl,--wrap=UpdSha256_File',
        '-o',os.path.relpath(OUT/'verification/integrity-update.exe',ROOT),'-LE:/BT3-Wii-tools/ucrt64/lib','-lSDL3','-lwinhttp','-lm']
    r=build.undefined.run(command,cwd=ROOT,capture_output=True,text=True);assert r.returncode==0,r.stderr
    seed=base64.b64decode((BASE/'online-lobby7-v013-20261030/private-signing/update_signing_key.txt').read_text('ascii').strip())
    report={}
    for case in ('valid','wrong_signature','bad_digest','bad_transfer_once','traversal','rollback','staged_readback','installed_readback'):
        with tempfile.TemporaryDirectory(dir=OUT/'verification',prefix='update-check-') as directory:
            tmp=Path(directory);game=tmp/'游戏目录';game.mkdir()
            original=(OUT/'verification/integrity-update.exe').read_bytes()
            (game/'Tenkaichi3Decomp.exe').write_bytes(original)
            shutil=__import__('shutil');shutil.copy2(OUT/'programs/SDL3.dll',game/'SDL3.dll')
            (game/'Tenkaichi3Decomp.dat').write_bytes(b'old-data')
            preserved=['bt3_settings.txt','bt3_wii_controls.ini','bt3_directory_admin.ini','bt3_gateway.json',
                'bt3_online_servers.ini','bt3_server_directory.ini','bt3_server.crt','saves/card.ps2',
                'wii_profiles/custom.ini','gamedata/disc/SLUS_216.78']
            for name in preserved:
                p=game/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b'personal')
            (game/'fonts').mkdir();(game/'fonts/fonts.tsv').write_bytes(b'mine.ttf\tMine\n')
            updates=tmp/'updates';folder=updates/'v0.18';folder.mkdir(parents=True);archive=folder/ASSET
            with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
                for name,data in [('Tenkaichi3Decomp.exe',b'new-game'),('Tenkaichi3Decomp.dat',b'new-data'),
                    ('启动游戏.exe',b'new-launcher'),('fonts/fonts.tsv',b'builtin.ttf\tBuiltin\n')]:z.writestr('Tenkaichi3Decomp/'+name,data)
                for name in preserved:z.writestr('Tenkaichi3Decomp/'+name,b'MUST-NOT-WRITE')
                if case=='traversal':z.writestr('Tenkaichi3Decomp/../escape.txt',b'escape')
            raw=archive.read_bytes();sig=key.sign(seed if case!='wrong_signature' else bytes(32),raw)
            (folder/(ASSET+'.sig')).write_text(sig.hex()+'\n','ascii')
            downloads=0
            lobby=Lobby({'database':str(tmp/'db.sqlite3'),'secret':'fixture','updates_dir':str(updates),'rooms':[{'id':'r','name':'Fixture'}]})
            parent=make_handler(lobby)
            class Handler(parent):
                def do_GET(self):
                    nonlocal downloads
                    if self.path.endswith('.zip'):
                        downloads+=1
                        if case=='bad_transfer_once' and downloads==1:
                            bad=bytearray(raw);bad[len(bad)//2]^=1
                            self.send_response(200);self.send_header('Content-Length',str(len(bad)));self.end_headers();self.wfile.write(bad);return
                    super().do_GET()
                def log_message(self,*args):pass
            server=ThreadingHTTPServer(('127.0.0.1',0),Handler);endpoint='http://127.0.0.1:'+str(server.server_port)
            assets=[{'name':p.name,'browser_download_url':endpoint+'/updates/v0.18/'+p.name,'size':p.stat().st_size,
                'digest':'sha256:'+('0'*64 if case=='bad_digest' and p==archive else hashlib.sha256(p.read_bytes()).hexdigest())}
                for p in [archive,folder/(ASSET+'.sig')]]
            (updates/'latest.json').write_text(json.dumps({'tag_name':'v0.18','body':'fixture','assets':assets}),'utf-8')
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            env=dict(os.environ,BT3_UPDATE_API=endpoint)
            for name in ('BT3_TEST_READBACK','BT3_UPDATE_FAIL_AT','BT3_MATCH_CURL'):env.pop(name,None)
            if case=='rollback':env['BT3_UPDATE_FAIL_AT']='1'
            if case in ('staged_readback','installed_readback'):env['BT3_TEST_READBACK']=case.split('_')[0]
            succeeds=case in ('valid','bad_transfer_once','staged_readback','installed_readback')
            try:
                r=subprocess.run([str(game/'Tenkaichi3Decomp.exe')]+([] if succeeds else ['fail']),cwd=game,env=env,capture_output=True,timeout=70)
                log=(r.stdout+r.stderr).decode('utf-8','replace');(OUT/'verification'/('update-integrity-'+case+'.log')).write_text(log,'utf-8')
                assert r.returncode==0,(case,log)
                for name in preserved:assert (game/name).read_bytes()==b'personal',(case,name)
                if succeeds:
                    assert (game/'Tenkaichi3Decomp.exe').read_bytes()==b'new-game'
                    assert (game/'Tenkaichi3Decomp.dat').read_bytes()==b'new-data'
                    assert b'mine.ttf\tMine' in (game/'fonts/fonts.tsv').read_bytes()
                    assert b'builtin.ttf\tBuiltin' in (game/'fonts/fonts.tsv').read_bytes()
                else:
                    assert (game/'Tenkaichi3Decomp.exe').read_bytes()==original
                    assert (game/'Tenkaichi3Decomp.dat').read_bytes()==b'old-data'
                    assert not (game/'启动游戏.exe').exists()
                if case in ('bad_transfer_once','staged_readback','installed_readback'):assert downloads==2,(case,downloads,log)
                if case in ('wrong_signature','bad_digest'):assert downloads==3,(case,downloads)
                assert not (tmp/'escape.txt').exists()
                report[case]={'passed':True,'archive_downloads':downloads}
            finally:server.shutdown();server.server_close();thread.join()
    (OUT/'verification/integrity-update.json').write_text(json.dumps(report,indent=2)+'\n','utf-8')
    print(json.dumps(report,indent=2))

if __name__=='__main__':run()
