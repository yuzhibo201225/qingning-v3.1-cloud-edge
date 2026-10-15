#!/usr/bin/env python3
"""Regenerate measured two-replica experiment timeline from event CSV."""
import argparse,csv
from pathlib import Path

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('events_csv')
    ap.add_argument('--out',default='elasticity_replicas.png')
    args=ap.parse_args()
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    with Path(args.events_csv).open(newline='',encoding='utf-8') as f:
        rows=list(csv.DictReader(f))
    rows=[r for r in rows if r['event']!='replica_removed' or r['reason']!='experiment_cleanup']
    rows=[r for r in rows if r['event']!='end_of_measurement' or r['observed']]
    xs=[float(r['elapsed_s']) for r in rows]
    ys=[int(r['observed']) for r in rows]
    if not xs: raise SystemExit('No events')
    fig,ax=plt.subplots(figsize=(8.8,3.6))
    ax.step(xs,ys,where='post',label='Observed healthy replicas',linewidth=1.8)
    colors={'demand_step_start':'#1d92aa','injected_replica_failure':'#be4f55','scale_down_decision':'#a18a45'}
    labels={'demand_step_start':'Demand step','injected_replica_failure':'Kill one replica','scale_down_decision':'Scale-down decision'}
    for r in rows:
        if r['event'] in colors:
            t=float(r['elapsed_s'])
            ax.axvline(t,color=colors[r['event']],linestyle='--',linewidth=1)
            ax.text(t+.16,2.16,labels[r['event']],fontsize=8,rotation=90,va='top',color=colors[r['event']])
    ax.set_xlim(0,max(xs)+.4)
    ax.set_ylim(0,2.35)
    ax.set_yticks([0,1,2]);ax.set_xlabel('Elapsed time (s)');ax.set_ylabel('Healthy replicas (count)')
    ax.grid(axis='y',alpha=.22)
    fig.tight_layout();fig.savefig(args.out,dpi=190)
    print(args.out)
if __name__=='__main__':main()
