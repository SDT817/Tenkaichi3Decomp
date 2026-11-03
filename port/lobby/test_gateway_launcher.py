"""Exercise the actual wrapper's child environment and socket lifetime.
No game, desktop interaction, remote server or system certificate store is used.
"""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import socket
import ssl
import subprocess
import sys
import tempfile
import threading

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT.parent/'Chinese-local-analysis-20261022/online-lobby3-ip2626-20261028'
EXE=OUT/'deployment/BT3Connect.exe'


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        raw=b'{"ok":true,"protocol":6}'
        self.send_response(200);self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
    def log_message(self,*args):pass


def run():
    with tempfile.TemporaryDirectory(dir=OUT/'verification',prefix='launcher-') as temporary:
        tmp=Path(temporary)
        subprocess.run([str(EXE),'-make-certificate','127.0.0.1','-certificate-directory',str(tmp)],check=True,capture_output=True)
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(tmp/'server.crt',tmp/'server.key')
        server.socket=context.wrap_socket(server.socket,server_side=True)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            remote=f'https://127.0.0.1:{server.server_port}'
            config=tmp/'gateway.json';config.write_text(json.dumps({'remote':remote,'certificate':'server.crt'}),'utf-8')
            child=tmp/'child.py'
            child.write_text('''import json,os,urllib.request
local=os.environ['BT3_LOBBY_GATEWAY_LOCAL']
remote=os.environ['BT3_LOBBY_GATEWAY_REMOTE']
with urllib.request.urlopen(local+'/healthz',timeout=10) as response: value=json.load(response)
assert value['ok'] and value['protocol']==6
print(json.dumps({'local':local,'remote':remote,'ok':True}))
''','utf-8')
            result=subprocess.run([str(EXE),'-config',str(config),'-run',sys.executable,'--',str(child)],
                capture_output=True,text=True,timeout=20)
            assert result.returncode==0,result.stdout+result.stderr
            value=json.loads(result.stdout)
            assert value['remote']==remote and value['ok']
            host,port=value['local'].removeprefix('http://').split(':')
            try:
                with socket.create_connection((host,int(port)),timeout=1):raise AssertionError('Bridge remained alive after child exit')
            except (ConnectionRefusedError,TimeoutError):pass
            # Production certificate's public IP is validated even when the
            # installer dials loopback for its on-server health check.
            production=OUT/'server-update-private'
            real_context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            real_context.load_cert_chain(production/'server.crt',production/'server.key')
            real_server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
            real_server.socket=real_context.wrap_socket(real_server.socket,server_side=True)
            real_thread=threading.Thread(target=real_server.serve_forever,daemon=True);real_thread.start()
            try:
                checked=subprocess.run([str(EXE),'-config',str(production/'client-check.json'),'-check','-check-address',f'127.0.0.1:{real_server.server_port}'],
                    capture_output=True,text=True,timeout=20)
                assert checked.returncode==0,checked.stdout+checked.stderr
            finally:real_server.shutdown();real_server.server_close();real_thread.join()
            report={'real_wrapper_child_environment':True,'bridge_available_during_child':True,'bridge_closed_after_child_exit':True,
                'production_certificate_public_IP_validated_with_loopback_dial':True,'game_launched':False}
            (OUT/'verification/launcher-tests.json').write_text(json.dumps(report,indent=2)+'\n','utf-8')
            print(json.dumps(report,indent=2))
        finally:server.shutdown();server.server_close();thread.join()


if __name__=='__main__':run()
