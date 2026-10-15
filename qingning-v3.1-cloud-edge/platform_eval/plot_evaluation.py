#!/usr/bin/env python3
"""Create reproducible labelled latency and throughput plots from load_summary.csv (requires matplotlib)."""
import argparse,csv
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('csv_path');p.add_argument('--out-dir',default='.')
a=p.parse_args();rows=list(csv.DictReader(open(a.csv_path,encoding='utf8')))
if len(rows)<5:raise SystemExit('At least five load levels required')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
out=Path(a.out_dir);out.mkdir(parents=True,exist_ok=True)
x=[int(r['concurrency']) for r in rows]
fig,ax=plt.subplots(figsize=(7.1,4.4))
for key,label in [('p50_ms','p50'),('p95_ms','p95'),('p99_ms','p99')]:ax.plot(x,[float(r[key]) if r[key] else float('nan') for r in rows],marker='o',label=label)
ax.set(xlabel='Concurrent clients',ylabel='Successful request latency (ms)',title='Isolated cloud order-ingest latency vs concurrent load')
ax.legend();ax.grid(True,alpha=.25);fig.tight_layout();fig.savefig(out/'latency.png',dpi=200);plt.close(fig)
fig,ax=plt.subplots(figsize=(7.1,4.4))
ax.plot(x,[float(r['throughput_rps']) for r in rows],marker='o',label='Throughput')
ax.set(xlabel='Concurrent clients',ylabel='Completed HTTP requests per second',title='Isolated cloud throughput vs load')
ax.grid(True,alpha=.25);fig.tight_layout();fig.savefig(out/'throughput.png',dpi=200);plt.close(fig)
print('Saved',out/'latency.png',out/'throughput.png')
