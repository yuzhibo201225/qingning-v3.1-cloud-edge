#!/usr/bin/env python3
"""Isolated REAL HTTP test against an ephemeral local-only cloud container.
Run on Ubuntu host that already has pi-cafe-classroom-cloud:local and Docker.
Never modifies the live cafe-cloud container or its /root/pi-cafe-classroom/cloud/data.
No third-party Python modules required.
"""
from __future__ import annotations
import argparse,csv,datetime,json,os,platform,random,secrets,shutil,signal,socket,sqlite3,statistics,subprocess,sys,threading,time,urllib.error,urllib.request,uuid
from concurrent.futures import ThreadPoolExecutor,as_completed
from pathlib import Path

TZ=datetime.timezone(datetime.timedelta(hours=8))

def sh(*args,check=True):
    p=subprocess.run(list(args),text=True,capture_output=True)
    if check and p.returncode:raise RuntimeError('Command failed: '+ ' '.join(args)+'\n'+p.stderr[-1500:])
    return p

def quantile(xs,p):
    if not xs:return None
    s=sorted(xs);f=(len(s)-1)*p;j=int(f);k=min(j+1,len(s)-1)
    return round(s[j]+(s[k]-s[j])*(f-j),3)

def order_payload():
    now=datetime.datetime.now(TZ).isoformat(timespec='seconds')
    return {'id':uuid.uuid4().hex,'table_no':random.randint(1,8),'source':'customer',
            'note':'','total_cents':2490,'status':'queued','created_at':now,
            'updated_at':now,'version':1,
            'items':[{'menu_id':1,'name':'Benchmark dish','qty':1,'price_cents':2490}]}

def http(base,payload,token,timeout=9):
    req=urllib.request.Request(base+'/api/sync/order',data=json.dumps(payload).encode('utf-8'),
      method='POST',headers={'Content-Type':'application/json','Authorization':'Bearer '+token})
    t=time.perf_counter();status=0;err=''
    try:
        with urllib.request.urlopen(req,timeout=timeout) as r:
            status=r.status;r.read()
    except urllib.error.HTTPError as e:
        status=e.code;err='HTTP_'+str(e.code)
    except (urllib.error.URLError,TimeoutError,OSError) as e:
        err=type(e).__name__
    return {'id':payload['id'],'success':int(status==200),'status':status,
            'latency_ms':round((time.perf_counter()-t)*1000,3),'error':err,
            'timestamp_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='milliseconds')}

def wait_health(base,seconds=45):
    stop=time.perf_counter()+seconds
    while time.perf_counter()<stop:
        try:
            with urllib.request.urlopen(base+'/health',timeout=1.4) as r:
                if r.status==200:return True
        except (OSError,urllib.error.URLError):pass
        time.sleep(.25)
    return False

def benchmark(base,token,levels,n,raw_writer):
    rows=[]
    for concurrency in levels:
        tasks=[order_payload() for _ in range(n)]
        start=time.perf_counter();results=[]
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            futures=[pool.submit(http,base,p,token) for p in tasks]
            for fut in as_completed(futures):
                result=fut.result();result['phase']='load';result['concurrency']=concurrency
                raw_writer.writerow(result);results.append(result)
        elapsed=time.perf_counter()-start
        good=[r['latency_ms'] for r in results if r['success']]
        row={'concurrency':concurrency,'requests':len(results),'success':len(good),
             'errors':len(results)-len(good),'error_rate_pct':round((len(results)-len(good))*100/len(results),3),
             'throughput_rps':round(len(results)/elapsed,3),'elapsed_s':round(elapsed,3),
             'p50_ms':quantile(good,.5),'p95_ms':quantile(good,.95),'p99_ms':quantile(good,.99)}
        rows.append(row)
        print('level:',json.dumps(row,ensure_ascii=False),flush=True)
    return rows

def fault_test(container,base,token,raw_writer):
    """Kill exactly the isolated test instance while requests continue, restart and retry failed IDs."""
    sent=[];results=[];lock=threading.Lock();stop=threading.Event()
    def driver():
        while not stop.is_set():
            payload=order_payload();result=http(base,payload,token,timeout=2)
            result.update(phase='failure_window',concurrency=1)
            with lock:sent.append(payload);results.append(result);raw_writer.writerow(result)
            time.sleep(.08)
    thread=threading.Thread(target=driver,daemon=True)
    thread.start();time.sleep(1.5)
    stop_cmd=sh('docker','stop','-t','1',container);down_t=time.perf_counter()
    time.sleep(2.0)
    restart_t=time.perf_counter();sh('docker','start',container)
    healthy=wait_health(base,40)
    recovered_s=round(time.perf_counter()-restart_t,3)
    time.sleep(1.0);stop.set();thread.join(timeout=5)
    if not healthy:raise RuntimeError('Isolated container failed to restart within 40s')
    failures=[p for p,r in zip(sent,results) if not r['success']]
    retried=[]
    for p in failures:
        r=http(base,p,token);r.update(phase='retry_after_recovery',concurrency=1)
        raw_writer.writerow(r);retried.append(r)
    result={'requests_during_window':len(results),
           'failed_before_retry':len(failures),
           'failure_rate_pct':round(100*len(failures)/max(1,len(results)),2),
           'forced_outage_s':round(restart_t-down_t,3),
           'restart_to_health_s':recovered_s,
           'retry_attempts':len(retried),'retry_success':sum(x['success'] for x in retried),
           'fault_target':'isolated single cloud container; live service untouched',
           'outcome':'Single instance unavailable during stop; client retry is required'}
    print('failure:',json.dumps(result,ensure_ascii=False),flush=True)
    return result,sent

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--port',type=int,default=15011)
    p.add_argument('--levels',default='1,5,10,25,50')
    p.add_argument('--requests-per-level',type=int,default=250)
    p.add_argument('--image',default='pi-cafe-classroom-cloud:local')
    p.add_argument('--app-dir',default='/root/pi-cafe-classroom/cloud',help='Cloud V3.1 source directory on Ubuntu host; mounted read-only')
    p.add_argument('--out',default=None,help='New output directory; default runs/run_UTC_TIMESTAMP')
    p.add_argument('--skip-failure',action='store_true')
    args=p.parse_args()
    levels=[int(a) for a in args.levels.split(',')]
    if len(set(levels))<5 or any(a<1 or a>100 for a in levels):p.error('Require >=5 distinct concurrency levels, 1..100')
    if args.requests_per_level<30 or args.requests_per_level>3000:p.error('requests-per-level must be 30..3000')
    if args.port<1024 or args.port>65535:p.error('invalid port')
    out=Path(args.out or ('runs/run_'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_'+secrets.token_hex(2))).resolve()
    if out.exists() and any(out.iterdir()):
        p.error('Output directory not empty: '+str(out)+'; choose a new --out to avoid mixing runs')
    out.mkdir(parents=True,exist_ok=True)
    appdir=Path(args.app_dir).resolve()
    required=['app.py','analytics.py','ai_engine.py','static/index.html']
    missing=[q for q in required if not (appdir/q).is_file()]
    if missing:p.error('V3.1 source files missing in --app-dir: '+', '.join(missing)+'; DO NOT test old V3 image as V3.1')

    marker=out/'.evaluation_marker'
    if not marker.exists():marker.write_text('This directory contains only artificial benchmark orders.\n')
    data=(out/'isolated_cloud_db');data.mkdir(exist_ok=True)
    env=out/'test.env';token=secrets.token_hex(28)
    env.write_text('SYNC_TOKEN='+token+'\nDASHBOARD_PIN='+secrets.token_hex(8)+'\nCLOUD_SESSION_SECRET='+secrets.token_hex(32)+'\nCLOUD_DB=/data/benchmark.sqlite3\nCLOUD_MEDIA_DIR=/data/media\nDEPLOY_MODE=test\n')
    env.chmod(0o600)
    run_id=uuid.uuid4().hex[:10];name='lh6041-eval-'+run_id
    base='http://127.0.0.1:'+str(args.port)
    # Do not bind to public IP; the benchmarking instance is reachable from the cloud host only.
    image_info=sh('docker','image','inspect',args.image,'--format','{{.Os}}/{{.Architecture}}').stdout.strip()
    print('Starting isolated benchmark. Image:',image_info,'localhost port:',args.port,flush=True)
    sh('docker','run','-d','--name',name,'--memory','250m','--env-file',str(env),
      '-v',str(data)+':/data',
      '-v',str(appdir/'app.py')+':/app/app.py:ro',
      '-v',str(appdir/'analytics.py')+':/app/analytics.py:ro',
      '-v',str(appdir/'ai_engine.py')+':/app/ai_engine.py:ro',
      '-v',str(appdir/'static')+':/app/static:ro',
      '-p','127.0.0.1:'+str(args.port)+':8000',args.image)
    rawpath=out/'raw_requests.csv';rows=[];failure={};sent=[];schema=['id','success','status','latency_ms','error','timestamp_utc','phase','concurrency']
    try:
        if not wait_health(base):raise RuntimeError('Could not start isolated app: '+sh('docker','logs',name,check=False).stdout[-1500:])
        with urllib.request.urlopen(base+'/health',timeout=4) as r:
            observed_version=json.load(r).get('version')
        if observed_version!='3.1-ai':
            raise RuntimeError('Version mismatch: expected 3.1-ai, found '+str(observed_version)+'. ABORTING.')
        print('Validated isolated target cloud version:',observed_version,flush=True)
        with rawpath.open('w',newline='',encoding='utf-8') as f:
            writer=csv.DictWriter(f,fieldnames=schema);writer.writeheader()
            rows=benchmark(base,token,levels,args.requests_per_level,writer)
            if not args.skip_failure:failure,sent=fault_test(name,base,token,writer)
        with (out/'load_summary.csv').open('w',newline='',encoding='utf-8') as f:
            w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
        with sqlite3.connect(data/'benchmark.sqlite3') as db:
            n=db.execute('SELECT COUNT(*) FROM orders').fetchone()[0]
            duplicates=db.execute('SELECT COUNT(*)-COUNT(DISTINCT id) FROM orders').fetchone()[0]
            missing=sum(1 for p in sent if not db.execute('SELECT 1 FROM orders WHERE id=?',(p['id'],)).fetchone())
        manifest={'measurement_type':'REAL HTTP requests to isolated Docker cloud container on this host',
                  'NOT':'Not production traffic, not edge ARM64 latency, not multi-tenant or autoscaling result',
                  'timestamp_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
                  'hostname':socket.gethostname(),'os':platform.platform(),'cpu_count':os.cpu_count(),
                  'image':args.image,'image_platform':image_info,'app_dir':str(appdir),'observed_version':observed_version,
                  'endpoint':'localhost isolated cloud sync ingest',
                  'requests_per_level':args.requests_per_level,'levels':levels,
                  'results':rows,'failure':failure,'db_total_orders':n,
                  'duplicate_primary_keys':duplicates,'missing_failure_window_orders_after_retries':missing,
                  'interpretation':'Autoscaling NOT implemented: single-instance baseline; scale-response target unmet/not tested.\n'+
                  'Load generator shares host with server; server uses SQLite single-writer.\n'+
                  'Single-instance stop produces downtime; no automatic failover.\n'+
                  'Retry behavior here is load-client retry, not a measurement of Raspberry Pi sync recovery.'}
        (out/'results.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print('RESULT FILES:',out/'results.json',rawpath,out/'load_summary.csv',flush=True)
        print('DB total orders:',n,'missing after retries:',missing,'duplicates:',duplicates,flush=True)
    finally:
        print('Removing ONLY test container',name,flush=True)
        sh('docker','rm','-f',name,check=False)
        env.unlink(missing_ok=True)  # do not persist test key

if __name__=='__main__':
    main()
