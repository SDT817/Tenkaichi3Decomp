"""Run the loopback directory, fixed rooms and UDP ping in one console."""
from pathlib import Path
import json
import threading
from http.server import ThreadingHTTPServer
from server import Lobby, load_config, make_handler
from directory_server import Directory
from ping_service import PingService

base=Path(__file__).resolve().parent
config=load_config(base/'demo.json')
lobby=Lobby(config)
ping=PingService(lobby)
ping.start()
dc=json.loads((base/'directory.local.json').read_text('utf-8-sig'))
dc['database']=str(base/dc['database'])
directory=Directory(dc)
servers=[ThreadingHTTPServer(('127.0.0.1',8787),make_handler(lobby)),
         ThreadingHTTPServer(('127.0.0.1',8788),make_handler(directory))]
threads=[]
for s in servers:
    s.daemon_threads=True
    t=threading.Thread(target=s.serve_forever,daemon=True);t.start();threads.append(t)
print('BT3 local rooms: http://127.0.0.1:8787',flush=True)
print('Shared directory: http://127.0.0.1:8788 | UDP RTT: 127.0.0.1:8787',flush=True)
print('Keep this window open. Ctrl+C stops both local services.',flush=True)
try:
    threading.Event().wait()
except KeyboardInterrupt:
    pass
finally:
    for s in servers:s.shutdown();s.server_close()
    for t in threads:t.join()
    ping.close()
