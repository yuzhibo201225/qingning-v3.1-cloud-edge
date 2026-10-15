#!/usr/bin/env python3
"""安全创建不同项目环境文件，不覆写现有 .env。"""
from pathlib import Path
import secrets,sys

root=Path(__file__).resolve().parents[1]
def create(name):
    d=root/name; target=d/'.env'
    if target.exists():
        print('已存在，绝不覆盖:',target)
        return
    body=(d/'.env.example').read_text()
    body=body.replace('REPLACE_WITH_RANDOM_PIN',str(secrets.randbelow(90000000)+10000000))
    body=body.replace('REPLACE_WITH_64_HEX_CHARS',secrets.token_hex(32))
    if name=='edge':
        body=body.replace('REPLACE_WITH_RANDOM_SHARED_SECRET',secrets.token_urlsafe(42))
    elif name=='cloud':
        edge=root/'edge'/'.env'
        if edge.exists():
            key=next((line.split('=',1)[1].strip() for line in edge.read_text().splitlines() if line.startswith('SYNC_TOKEN=')),'')
            body=body.replace('REPLACE_WITH_SAME_EDGE_SYNC_TOKEN',key)
        else:
            print('请先生成 edge/.env，再生成 cloud/.env');sys.exit(1)
    target.write_text(body)
    target.chmod(0o600)
    print('已创建:',target)

if __name__=='__main__':
    for part in (sys.argv[1:] or ['edge','cloud']):
        if part not in ('edge','cloud'):sys.exit('选项只支持 edge cloud')
        create(part)
