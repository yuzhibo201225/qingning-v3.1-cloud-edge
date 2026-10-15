#!/usr/bin/env python3
"""Run on Raspberry Pi. Read-only snapshot, no Wi-Fi changes and no secrets."""
import argparse,datetime,json,platform,socket,subprocess,urllib.request

def cmd(*parts):
    try:r=subprocess.run(parts,capture_output=True,text=True,timeout=4);return r.stdout.strip()[:450] if r.returncode==0 else 'NOT_AVAILABLE'
    except Exception:return 'NOT_AVAILABLE'

def fetch(url):
    try:
        with urllib.request.urlopen(url,timeout=6) as r:return dict(ok=r.status==200,status=r.status,body=r.read(180).decode('utf-8',errors='replace'))
    except Exception as e:return dict(ok=False,error=type(e).__name__+': '+str(e)[:100])

p=argparse.ArgumentParser();p.add_argument('--label',required=True);p.add_argument('--out',default=None);args=p.parse_args()
data=dict(label=args.label,captured_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),hostname=socket.gethostname(),os=platform.platform(),
          addresses=cmd('hostname','-I'),route=cmd('ip','-4','route','get','1.1.1.1'),
          wlan=cmd('ip','-4','-o','addr','show','wlan0'),
          edge_local_health=fetch('http://127.0.0.1:18080/health'),
          public_cloud_health=fetch('http://CLOUD_PUBLIC_IP:15001/health'))
blob=json.dumps(data,ensure_ascii=False,indent=2)+'\n';print(blob)
if args.out:
    from pathlib import Path
    path=Path(args.out);path.write_text(blob,encoding='utf-8');print('Saved to',path)
