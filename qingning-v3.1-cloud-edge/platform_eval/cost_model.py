#!/usr/bin/env python3
"""Explicit-assumption scenario model: 1x/10x/100x. NOT actual billing evidence.
Uses only Python stdlib.  Refuses to calculate with missing assumptions.
"""
import argparse,csv,json,math
from pathlib import Path
FIELDS=['vm_monthly_cny','vm_sustainable_rps','target_utilisation','tenants','orders_per_day',
        'requests_per_order','storage_start_gb','gb_added_per_1000_orders',
        'storage_cny_per_gb_month','monitoring_monthly_cny','ops_monthly_cny','variable_cny_per_1000_requests']
def main():
    p=argparse.ArgumentParser();p.add_argument('assumptions');p.add_argument('--out',default='cost_scenarios.csv')
    a=p.parse_args();v=json.loads(Path(a.assumptions).read_text())
    missing=[f for f in FIELDS if f not in v or v[f] is None]
    if missing:raise SystemExit('MISSING INPUTS: '+', '.join(missing)+'\nUse provider bill, observed benchmark and explicit assumptions; do not invent actual numbers.')
    nonnegative=['storage_start_gb','gb_added_per_1000_orders','storage_cny_per_gb_month',
                 'monitoring_monthly_cny','ops_monthly_cny','variable_cny_per_1000_requests']
    if any(float(v[f])<0 for f in nonnegative):raise SystemExit('Cost inputs cannot be negative')
    positive=set(FIELDS)-set(nonnegative)
    if any(float(v[f])<=0 for f in positive):raise SystemExit('VM, capacity, utilisation, tenants and demand must be positive')
    if not 0<v['target_utilisation']<=1:raise SystemExit('target_utilisation needs 0<value<=1')
    result=[]
    for scale in (1,10,100):
        tenants=int(v['tenants']*scale)
        orders=v['orders_per_day']*scale
        requests=orders*v['requests_per_order']*30
        mean_rps=requests/(30*86400)
        # capacity planning parameter is transparent; averaged demand is an optimistic lower bound
        instances=max(1,math.ceil(mean_rps/(v['vm_sustainable_rps']*v['target_utilisation'])))
        storage=v['storage_start_gb']+v['gb_added_per_1000_orders']*(orders*30/1000)
        compute=instances*v['vm_monthly_cny']
        data_storage=storage*v['storage_cny_per_gb_month']
        variable=requests/1000*v['variable_cny_per_1000_requests']
        fixed=compute+v['monitoring_monthly_cny']+v['ops_monthly_cny']
        total=fixed+data_storage+variable
        result.append(dict(scale=f'{scale}x',tenants=tenants,orders_month=round(orders*30),
            requests_month=round(requests),mean_rps=round(mean_rps,3),vm_count=instances,
            storage_gb=round(storage,3),fixed_cny=round(fixed,2),variable_cny=round(data_storage+variable,2),
            total_cny=round(total,2),cny_per_tenant_month=round(total/tenants,3),
            cny_per_1000_requests=round(total/requests*1000,3),
            fixed_share_pct=round(fixed/total*100,2),
            evidence='SCENARIO MODEL, NOT OBSERVED COST'))
    with open(a.out,'w',newline='',encoding='utf8') as fp:
        w=csv.DictWriter(fp,fieldnames=list(result[0]));w.writeheader();w.writerows(result)
    print(json.dumps(result,ensure_ascii=False,indent=2));print('Saved:',a.out)
    print('WARNING: Mean RPS underestimates peak capacity need; model omits charges not entered in assumptions.')
if __name__=='__main__':main()
