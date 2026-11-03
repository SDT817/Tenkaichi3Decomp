"""Actual native updater: notes, signature/hash, install, preservation, rollback."""
import base64
from http.server import ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import zipfile
from server import Lobby,make_handler
from publish_update import key,ASSET

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT.parent/'Chinese-local-analysis-20261022/online-lobby10-v016-20261101/verification'
import sys
sys.path.insert(0,str(ROOT/'local'))
import build_windows as build

def run():
    cmd=['gcc','-m32','-std=gnu99','-O2','-Iport/src/gs','-Iport/build/gen/gs','port/lobby/update_probe.c',
         *[str(build.undefined.OBJ/(n+'.o')) for n in ['gs_net_update','gs_update_sign','gs_update_crypto']],
         'port/src/gs/update_monocypher.c',
         '-o',os.path.relpath(OUT/'update_probe.exe',ROOT),'-LE:/BT3-Wii-tools/ucrt64/lib','-lSDL3','-lwinhttp','-lm']
    r=build.undefined.run(cmd,cwd=ROOT,capture_output=True,text=True)
    assert r.returncode==0,r.stderr
    seed=base64.b64decode((OUT.parents[1]/'online-lobby7-v013-20261030/private-signing/update_signing_key.txt').read_text('ascii').strip())
    report={}
    for case in ['valid','wrong_signature','bad_digest','traversal','rollback']:
        with tempfile.TemporaryDirectory(dir=OUT,prefix='update-') as directory:
            tmp=Path(directory); game=tmp/'游戏目录';game.mkdir()
            original=(OUT/'update_probe.exe').read_bytes()
            (game/'Tenkaichi3Decomp.exe').write_bytes(original)
            (game/'SDL3.dll').write_bytes(Path('E:/PS2 yizhi/Lobby/管理员端/SDL3.dll').read_bytes())
            (game/'Tenkaichi3Decomp.dat').write_bytes(b'old-data')
            preserved=['bt3_settings.txt','bt3_wii_controls.ini','bt3_directory_admin.ini','bt3_gateway.json',
                       'bt3_online_servers.ini','bt3_server_directory.ini','bt3_server.crt','saves/card.ps2',
                       'wii_profiles/custom.ini','gamedata/disc/SLUS_216.78']
            for name in preserved:
                p=game/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b'personal-data')
            updates=tmp/'updates';folder=updates/'v0.17';folder.mkdir(parents=True)
            archive=folder/ASSET
            with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
                z.writestr('Tenkaichi3Decomp/Tenkaichi3Decomp.exe',b'new-game')
                z.writestr('Tenkaichi3Decomp/Tenkaichi3Decomp.dat',b'new-data')
                z.writestr('Tenkaichi3Decomp/启动游戏.exe',b'new-launcher')
                for name in preserved:z.writestr('Tenkaichi3Decomp/'+name,b'MUST-NOT-WRITE')
                if case=='traversal':z.writestr('Tenkaichi3Decomp/../escape.txt',b'escape')
            raw=archive.read_bytes()
            signature=key.sign(seed,raw) if case!='wrong_signature' else key.sign(bytes(32),raw)
            (folder/(ASSET+'.sig')).write_text(signature.hex()+'\n','ascii')
            lobby=Lobby({'database':str(tmp/'db.sqlite3'),'secret':'fixture', 'updates_dir':str(updates),
                         'rooms':[{'id':'r','name':'Fixture'}]})
            server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(lobby))
            endpoint='http://127.0.0.1:'+str(server.server_port)
            import hashlib
            assets=[{'name':p.name,'browser_download_url':endpoint+'/updates/v0.17/'+p.name,'size':p.stat().st_size,
                     'digest':'sha256:'+('0'*64 if case=='bad_digest' and p==archive else hashlib.sha256(p.read_bytes()).hexdigest())}
                    for p in [archive,folder/(ASSET+'.sig')]]
            (updates/'latest.json').write_text(json.dumps({'tag_name':'v0.17','body':'测试公告：签名更新',
                                                          'assets':assets},ensure_ascii=False),'utf-8')
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            env=dict(os.environ,BT3_UPDATE_API=endpoint)
            env['PATH']=r'E:\BT3-Wii-tools\mingw64\bin;E:\BT3-Wii-tools\ucrt64\bin;'+env['PATH']
            if case=='rollback':env['BT3_UPDATE_FAIL_AT']='1'
            try:
                r=subprocess.run([str(game/'Tenkaichi3Decomp.exe')]+([] if case=='valid' else ['fail']),cwd=game,
                                 env=env,capture_output=True,timeout=40)
                log=(r.stdout+r.stderr).decode('utf-8','replace')
                (OUT/('update-'+case+'.log')).write_text(log,'utf-8')
                assert r.returncode==0,(case,log)
                for name in preserved:assert (game/name).read_bytes()==b'personal-data',(case,name)
                if case=='valid':
                    assert (game/'Tenkaichi3Decomp.exe').read_bytes()==b'new-game'
                    assert (game/'Tenkaichi3Decomp.dat').read_bytes()==b'new-data'
                    assert (game/'启动游戏.exe').read_bytes()==b'new-launcher'
                else:
                    assert (game/'Tenkaichi3Decomp.exe').read_bytes()==original
                    assert (game/'Tenkaichi3Decomp.dat').read_bytes()==b'old-data'
                    assert not (game/'启动游戏.exe').exists()
                assert not (tmp/'escape.txt').exists()
                report[case]=True
            finally:
                server.shutdown();server.server_close();thread.join()
    (OUT/'private-update-tests.json').write_text(json.dumps(report,indent=2)+'\n','utf-8')
    print(json.dumps(report,indent=2))

if __name__=='__main__':run()
