"""Exercise the deployed public-IP identity with real Caddy and no TLS SNI.

Use the existing certificate without changing its key. Dial only loopback;
the client still verifies the public IP, signature, expiry and trust chain.
"""
from contextlib import closing
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hashlib
import json
from pathlib import Path
import os
import socket
import ssl
import subprocess
import tempfile
import threading
import time

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT.parent/'Chinese-local-analysis-20261022/online-lobby3-ip2626-20261028'
CADDY = OUT.parent/'online-lobby2-preview-20261027/deployment/runtime/caddy/caddy.exe'
PACKAGE = OUT/'server-update-private'
IP = '114.132.102.42'


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        assert self.path == '/healthz', self.path
        data = b'{"ok":true,"protocol":6}'
        self.send_response(200)
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        assert self.path in ('/lobby/v1/request', '/directory/v1/request'), self.path
        assert self.headers.get('X-BT3-Lobby-Key') == 'regression-test'
        assert self.rfile.read(int(self.headers['Content-Length'])) == b'{"op":"list"}'
        data = json.dumps({'ok':True,'path':self.path}).encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass


def run():
    verification = OUT/'verification'
    baseline = (OUT/'records/packaging-tools/prepare_distribution.py').read_text('utf-8')
    # The first released template is immutable evidence of the failing case.
    start = baseline.index("write(SERVER/'Caddyfile-IP2626.template','''")
    original = baseline[start:].split("'''", 2)[1]
    assert 'default_sni' not in original
    fixed = (Path(__file__).parent/'deploy/Caddyfile-IP2626.template').read_text('utf-8')
    assert fixed == original.replace('    admin off\n', '    admin off\n    default_sni '+IP+'\n', 1)
    context = ssl.create_default_context(cafile=str(PACKAGE/'server.crt'))
    result = {'public_certificate_IP': IP, 'public_certificate_SHA256':
              hashlib.sha256(ssl.PEM_cert_to_DER_cert((PACKAGE/'server.crt').read_text('ascii'))).hexdigest(),
              'dial_target': '127.0.0.1', 'system_certificate_store_modified': False,
              'game_or_remote_service_started': False, 'cases': []}
    backend = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=backend.serve_forever, daemon=True)
    thread.start()
    try:
        with tempfile.TemporaryDirectory(dir=verification, prefix='ip-caddy-') as temporary:
            temp = Path(temporary)
            for name, template in [('original', original), ('fixed', fixed)]:
                with closing(socket.socket()) as reservation:
                    reservation.bind(('127.0.0.1', 0))
                    port = reservation.getsockname()[1]
                config = template.replace('@@ROOT@@/config/tls-ip2626', PACKAGE.as_posix())
                config = config.replace(':2626 {', ':'+str(port)+' {').replace('bind 0.0.0.0', 'bind 127.0.0.1')
                config = config.replace('127.0.0.1:8787', '127.0.0.1:'+str(backend.server_port))
                config = config.replace('127.0.0.1:8788', '127.0.0.1:'+str(backend.server_port))
                config_path = temp/('Caddyfile-'+name)
                config_path.write_text(config, 'utf-8')
                check_config = temp/('check-'+name+'.json')
                check_config.write_text(json.dumps({'remote':f'https://{IP}:{port}',
                    'certificate':str(PACKAGE/'server.crt')}), 'utf-8')
                log_path = verification/('ip2626-caddy-'+name+'.log')
                with log_path.open('wb') as log:
                    process = subprocess.Popen([str(CADDY),'run','--config',str(config_path),'--adapter','caddyfile'],
                        cwd=temp, env=dict(os.environ,XDG_DATA_HOME=str(temp/'data'),XDG_CONFIG_HOME=str(temp/'config')),
                        stdout=log, stderr=log, creationflags=subprocess.CREATE_NO_WINDOW)
                    try:
                        for attempt in range(60):
                            try:
                                with socket.create_connection(('127.0.0.1',port),timeout=.2):break
                            except OSError:
                                if process.poll() is not None:raise AssertionError(log_path.read_text('utf-8'))
                                time.sleep(.1)
                        else:raise AssertionError('TLS listener did not start')
                        check = subprocess.run([str(PACKAGE/'BT3Connect.exe'),'-config',str(check_config),'-check',
                            '-check-address',f'127.0.0.1:{port}'],capture_output=True,text=True,timeout=20)
                        if name == 'original':
                            assert check.returncode != 0 and 'tls: internal error' in check.stderr, check.stdout+check.stderr
                        else:
                            assert check.returncode == 0, check.stdout+check.stderr
                            # Python independently omits SNI for an IP, while checking that same IP.
                            for path in ('/healthz','/lobby/v1/request','/directory/v1/request'):
                                if path == '/healthz':
                                    request = 'GET '+path+' HTTP/1.1\r\n'
                                    body = ''
                                else:
                                    body = '{"op":"list"}'
                                    request = ('POST '+path+' HTTP/1.1\r\nContent-Type: application/json\r\n'
                                        'X-BT3-Lobby-Key: regression-test\r\nContent-Length: '+str(len(body))+'\r\n')
                                with socket.create_connection(('127.0.0.1',port),timeout=5) as raw:
                                    with context.wrap_socket(raw, server_hostname=IP) as tls:
                                        tls.sendall((request+f'Host: {IP}:{port}\r\nConnection: close\r\n\r\n'+body).encode('ascii'))
                                        response = b''
                                        while chunk := tls.recv(4096):response += chunk
                                        assert b'200 OK' in response, response
                                        payload = json.loads(response.split(b'\r\n\r\n',1)[1])
                                        assert payload.get('protocol') == 6 if path == '/healthz' else payload.get('path') == path, payload
                        result['cases'].append({'config':name,'native_client_exit_code':check.returncode,
                            'stdout':check.stdout.strip(),'stderr':check.stderr.strip(),
                            'independent_python_IP_validation':name == 'fixed',
                            'health_lobby_directory_routes_and_auth_header':name == 'fixed'})
                    finally:
                        if process.poll() is None:process.terminate();process.wait(timeout=10)
    finally:
        backend.shutdown();backend.server_close();thread.join()
    result['regression_reproduced_and_fixed'] = True
    (verification/'ip2626-caddy-regression.json').write_text(json.dumps(result,indent=2)+'\n','utf-8')
    print(json.dumps(result,indent=2),flush=True)


if __name__ == '__main__':run()
