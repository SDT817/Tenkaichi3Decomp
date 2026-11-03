"""Generate matched configs locally; never deploys, opens ports, or starts services."""
import argparse
import ipaddress
import json
import os
from pathlib import Path
import re
import secrets

if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--ipv4',required=True)
    parser.add_argument('--domain',required=True)
    parser.add_argument('--out',type=Path,default=Path('generated-private'))
    args=parser.parse_args()
    address=ipaddress.IPv4Address(args.ipv4)
    if not address.is_global:parser.error('Use the VPS public IPv4 address')
    if not re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9.-]{0,250}[A-Za-z0-9])?',args.domain) or '..' in args.domain:
        parser.error('Invalid DNS name')
    if args.out.exists():parser.error('Output already exists; preserve existing secrets')
    args.out.mkdir(parents=True,mode=0o700)
    root=Path(__file__).parent
    shared=secrets.token_hex(32)
    access=secrets.token_hex(24)
    config=json.loads((root/'server.example.json').read_text('utf-8'))
    config['access_key']=access
    config['turn']['secret']=shared
    config['turn']['server']=f'{address}:3478'
    (args.out/'server.json').write_text(json.dumps(config,ensure_ascii=False,indent=2)+'\n','utf-8')
    for src,dest in [('turnserver.conf.example','turnserver.conf'),('nginx.conf.example','nginx.conf')]:
        text=(root/src).read_text('utf-8').replace('PUBLIC_IPV4',str(address)).replace('YOUR_DOMAIN',args.domain).replace('CHANGE_TO_THE_SAME_COTURN_SHARED_SECRET',shared)
        (args.out/dest).write_text(text,'utf-8')
    (args.out/'friends-server.txt').write_text(f'BT3SERVER1:好友服务器|https://{args.domain}|{access}\n','utf-8')
    for p in args.out.iterdir():os.chmod(p,0o600)
    print('Generated matched configuration in',args.out.resolve())
    print('Share only friends-server.txt with your players. Keep server.json and turnserver.conf private.')
