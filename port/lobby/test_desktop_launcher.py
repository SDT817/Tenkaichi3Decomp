"""Real GUI-subsystem EXE launch, Unicode paths, TLS and child lifetime; no game."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import json
import os
import shutil
import socket
import ssl
import subprocess
import tempfile
import threading

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT.parent / 'Chinese-local-analysis-20261022/online-lobby8-v014-20261030'

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        assert self.path == '/healthz'
        raw = b'{"ok":true,"protocol":6}'
        self.send_response(200)
        self.send_header('Content-Length', str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)
    def log_message(self, *args):
        pass

def main():
    with tempfile.TemporaryDirectory(dir=OUT/'verification', prefix='launcher-') as temporary:
        tmp = Path(temporary)
        folder = tmp/'中文目录 with spaces'
        folder.mkdir()
        subprocess.run([str(OUT/'programs/BT3Connect.exe'), '-make-certificate', '127.0.0.1',
                        '-certificate-directory', str(folder/'identity')], check=True, capture_output=True)
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(folder/'identity/server.crt', folder/'identity/server.key')
        server.socket = context.wrap_socket(server.socket, server_side=True)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            remote = f'https://127.0.0.1:{server.server_port}'
            (folder/'bt3_gateway.json').write_text(json.dumps({'remote': remote, 'certificate': 'identity/server.crt'}), 'utf-8')
            shutil.copy2(OUT/'programs/启动游戏.exe', folder/'启动游戏.exe')
            shutil.copy2(OUT/'verification/desktop_child.exe', folder/'Tenkaichi3Decomp.exe')
            env = dict(os.environ, BT3_LOBBY_GATEWAY_REMOTE='replaced', BT3_LOBBY_GATEWAY_LOCAL='replaced')
            env.pop('BT3_PRESENT_MODE', None)
            for _ in range(2):
                run = subprocess.run([str(folder/'启动游戏.exe')], cwd=OUT, env=env, timeout=20,
                                     creationflags=subprocess.CREATE_NO_WINDOW)
                assert run.returncode == 0, (folder/'bt3-launcher.log').read_text('utf-8', errors='replace')
                result = json.loads((folder/'desktop-child.json').read_text('utf-8'))
                assert Path(result['cwd']).resolve() == folder.resolve(), result
                assert result['remote'] == remote and result['health'] == {'ok': True, 'protocol': 6}, result
                assert result['present_mode_env'] == '', result
                host, port = result['local'].removeprefix('http://').split(':')
                try:
                    with socket.create_connection((host, int(port)), timeout=1):
                        raise AssertionError('Bridge remained alive after the game child exited')
                except (ConnectionRefusedError, TimeoutError):
                    pass
        finally:
            server.shutdown()
            server.server_close()
            thread.join()
    report = {'real_windows_GUI_launcher': True, 'no_arguments_required': True,
              'unrelated_working_directory': True, 'unicode_and_spaces': True,
              'TLS_bridge_reachable_from_child': True, 'stale_gateway_environment_replaced': True,
              'bridge_closed_after_child': True, 'relaunch_passed': True,
              'present_mode_not_injected_by_launcher': True, 'actual_game_started': False}
    (OUT/'verification/desktop-launcher.json').write_text(json.dumps(report, indent=2)+'\n', 'utf-8')
    print(json.dumps(report, indent=2))

if __name__ == '__main__':
    main()
