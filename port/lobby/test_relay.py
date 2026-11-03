"""Protocol fixture, NOT coturn. Verifies existing client wire/auth behavior.

This is deliberately not shipped as a production TURN service.
"""
import base64
import hashlib
import hmac
import json
import os
from pathlib import Path
import socket
import struct
import subprocess
import threading
import time

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT.parent/'Chinese-local-analysis-20261022/online-lobby5-official1391-20261029/verification'
COOKIE=b'\x21\x12\xa4\x42'

def attr(kind,data):
    return struct.pack('!HH',kind,len(data))+data+b'\0'*((-len(data))%4)

def attrs(packet):
    pos=20
    out={}
    while pos+4<=len(packet):
        kind,size=struct.unpack_from('!HH',packet,pos)
        out[kind]=(packet[pos+4:pos+4+size],pos)
        pos+=4+(size+3)//4*4
    return out

def xor_address(port):
    return b'\0\1'+struct.pack('!H',port^0x2112)+bytes(a^b for a,b in zip(socket.inet_aton('127.0.0.1'),COOKIE))

def run():
    env=dict(os.environ,PATH=r'E:\BT3-Wii-tools\mingw64\bin;E:\BT3-Wii-tools\ucrt64\bin;'+os.environ['PATH'])
    username=f'{int(time.time())+32400}:fixture-session'
    credential=base64.b64encode(hmac.new(b'fixture-secret',username.encode(),hashlib.sha1).digest()).decode()
    realm=b'BT3_PRIVATE_LOBBY';nonce=b'fixture-nonce'
    key=hashlib.md5(username.encode()+b':'+realm+b':'+credential.encode()).digest()
    udp=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);udp.bind(('127.0.0.1',0));udp.settimeout(.1)
    done=threading.Event();errors=[];counts={'challenge':0,'allocate':0,'permit':0,'send_indication':0,'channel_bind':0,'channel_data':0,'refresh':0,'close':0,'integrity':0}
    peer=None;channel=0;last_ping=0;client=None
    def packet(kind,tx,data=b''):
        return struct.pack('!HH',kind,len(data))+COOKIE+tx+data
    def send_ping():
        nonlocal last_ping
        if channel:
            data=struct.pack('!HH',channel,4)+b'PING'
        else:
            data=packet(0x0017,b'fixture-ping',attr(0x0012,xor_address(45000))+attr(0x0013,b'PING'))
        udp.sendto(data,client);last_ping=time.monotonic()
    def serve():
        nonlocal client,channel,peer
        try:
            while not done.is_set():
                try:p,client=udp.recvfrom(2048)
                except socket.timeout:
                    if peer and time.monotonic()-last_ping>.65 and counts['send_indication']+counts['channel_data']<3:send_ping()
                    continue
                kind=struct.unpack_from('!H',p)[0]
                if 0x4000<=kind<=0x7fff:
                    assert p[4:8]==b'PONG';counts['channel_data']+=1;continue
                a=attrs(p)
                if kind==0x0003 and 0x0006 not in a:
                    counts['challenge']+=1
                    data=attr(0x0009,b'\0\0\4\1Unauthorized')+attr(0x0014,realm)+attr(0x0015,nonce)
                    udp.sendto(packet(0x0113,p[8:20],data),client);continue
                if kind in (0x0003,0x0008,0x0009,0x0004):
                    assert a[0x0006][0]==username.encode() and a[0x0014][0]==realm and a[0x0015][0]==nonce
                    value,pos=a[0x0008]
                    prefix=bytearray(p[:pos]);struct.pack_into('!H',prefix,2,pos+24-20)
                    assert hmac.compare_digest(hmac.new(key,prefix,hashlib.sha1).digest(),value),'MESSAGE-INTEGRITY mismatch'
                    counts['integrity']+=1
                if kind==0x0003:
                    counts['allocate']+=1
                    udp.sendto(packet(0x0103,p[8:20],attr(0x0016,xor_address(50000))),client)
                elif kind==0x0008:
                    counts['permit']+=1;peer=True
                    udp.sendto(packet(0x0108,p[8:20]),client);send_ping()
                elif kind==0x0016:
                    assert a[0x0013][0]==b'PONG';counts['send_indication']+=1
                elif kind==0x0009:
                    counts['channel_bind']+=1;channel=struct.unpack_from('!H',a[0x000c][0])[0]
                    udp.sendto(packet(0x0109,p[8:20]),client)
                elif kind==0x0004:
                    lifetime=struct.unpack('!I',a[0x000d][0])[0]
                    counts['refresh' if lifetime else 'close']+=1
                    udp.sendto(packet(0x0104,p[8:20]),client)
        except Exception as e:errors.append(str(e))
    thread=threading.Thread(target=serve,daemon=True);thread.start()
    try:
        result=subprocess.run([str(OUT/'relay_probe.exe'),f'127.0.0.1:{udp.getsockname()[1]}',username,credential],
                              cwd=ROOT,env=env,capture_output=True,timeout=15)
        text=result.stdout.decode(errors='replace')+result.stderr.decode(errors='replace')
        (OUT/'TURN-fixture.log').write_text(text,'utf-8')
        assert result.returncode==0 and not errors,(result.returncode,text,errors,counts)
        assert all(counts[k]>0 for k in counts),counts
        report={'fixture':'deterministic local UDP; NOT a coturn deployment','existing_relay_source_unchanged':True,
                'REST_credentials_and_long_term_integrity':True,'counts':counts,'real_coturn_tested':False,'game_launched':False}
        (OUT/'TURN-fixture-tests.json').write_text(json.dumps(report,indent=2)+'\n','utf-8')
        print(json.dumps(report,indent=2),flush=True)
    finally:
        done.set();thread.join(timeout=2);udp.close()

if __name__=='__main__':run()
