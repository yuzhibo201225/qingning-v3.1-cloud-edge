#!/usr/bin/env python3
"""LH6041 V3.1 isolated application-replica elasticity/failover REAL HTTP experiment.

Run on the same Alibaba VM where the V3.1 Docker image already exists.
NOT production HA, not VM autoscaling, not a demonstration of zone resilience.
Only binds 127.0.0.1:15110 (proxy), :15121 and :15122 (test backends),
with isolated synthetic DB and test token. No changes to cafe-cloud:15001.

Output: autoscale_events.csv, proxy_requests.csv, results.json (actual observations).
System Python standard library only; Docker CLI must be installed.
"""
from __future__ import annotations
import argparse,collections,csv,datetime,json,os,platform,random,secrets,socket,sqlite3,subprocess,sys,threading,time,urllib.error,urllib.request,uuid
from concurrent.futures import ThreadPoolExecutor,as_completed
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path

UTC=datetime.timezone.utc

def utcnow():return datetime.datetime.now(UTC).isoformat(timespec='milliseconds')
def sh(*argv,check=True):
    p=subprocess.run(list(argv),capture_output=True,text=True)
    if p.returncode and check:raise RuntimeError('COMMAND '+repr(argv)+'\n'+p.stderr[-1400:])
    return p

def free_mem_mib():
    d={}
    for s in Path('/proc/meminfo').read_text().splitlines():
        if ':' in s:
            k,v=s.split(':',1)
            try:d[k]=int(v.strip().split()[0])//1024
            except (ValueError,IndexError):pass
    return d.get('MemAvailable',0)

def health(url,timeout=0.8):
    try:
        with urllib.request.urlopen(url+'/health',timeout=timeout) as r:return r.status==200 and json.load(r).get('version')=='3.1-ai'
    except Exception:return False

def wait_health(url,timeout=20):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        if health(url):return True
        time.sleep(.17)
    return False

def quantile(xs,p):
    if not xs:return None
    z=sorted(xs);s=(len(z)-1)*p;j=int(s);k=min(j+1,len(z)-1)
    return round(z[j]+(z[k]-z[j])*(s-j),3)

def order_payload():
    now=datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat(timespec='seconds')
    return dict(id=uuid.uuid4().hex,table_no=random.randint(1,8),source='customer',note='',total_cents=2490,status='queued',created_at=now,updated_at=now,version=1,items=[dict(menu_id=1,name='Elasticity Test Dish',qty=1,price_cents=2490)])

class Orchestrator:
    def __init__(self,args,out,token):
        self.args=args;self.out=out;self.token=token;self.prefix='lh6041-ha-'+secrets.token_hex(4)
        self.lock=threading.RLock();self.workers={};self.desired=1;self.events=[];self.req_times=collections.deque();self.last_busy=time.monotonic();self.rr=0
        self.start_time=time.monotonic();self.stopped=threading.Event();self.env=out/'test.env'
        self.db_dir=out/'isolated_db';self.db_dir.mkdir(exist_ok=True)
        self.env.write_text('SYNC_TOKEN='+token+'\nDASHBOARD_PIN='+secrets.token_hex(9)+'\nCLOUD_SESSION_SECRET='+secrets.token_hex(32)+'\nCLOUD_DB=/data/ha_test.sqlite3\nCLOUD_MEDIA_DIR=/data/media\nDEPLOY_MODE=test\n')
        self.env.chmod(0o600)
        self.app=Path(args.app_dir).resolve()
        self.backend_ports=[args.backend_port,args.backend_port+1]
        self.in_progress=False
    def event(self,typ,**kw):
        item=dict(timestamp_utc=utcnow(),elapsed_s=round(time.monotonic()-self.start_time,3),event=typ,desired=self.desired,observed=len(self.workers),**kw)
        with self.lock:self.events.append(item)
        print('EVENT',json.dumps(item,ensure_ascii=False),flush=True)
    def start_worker(self,slot,reason):
        name=self.prefix+'-'+str(slot);port=self.backend_ports[slot-1]
        if slot == 2 and free_mem_mib() < 195:
            self.event('scale_up_blocked_low_memory',slot=slot,available_mib=free_mem_mib())
            raise RuntimeError('Refusing second replica: less than 195 MiB available. Protecting live service.')
        self.event('replica_start_requested',slot=slot,reason=reason,port=port)
        argv=['docker','run','-d','--name',name,'--memory',str(self.args.memory_mb)+'m','--restart=no','--env-file',str(self.env),
              '-v',str(self.db_dir)+':/data','-v',str(self.app/'app.py')+':/app/app.py:ro',
              '-v',str(self.app/'analytics.py')+':/app/analytics.py:ro','-v',str(self.app/'ai_engine.py')+':/app/ai_engine.py:ro',
              '-v',str(self.app/'static')+':/app/static:ro','-p','127.0.0.1:'+str(port)+':8000',self.args.image]
        try:
            sh(*argv)
            if not wait_health('http://127.0.0.1:'+str(port),24):
                raise RuntimeError('replica did not become healthy: '+sh('docker','logs','--tail','15',name,check=False).stdout[-1200:])
            with self.lock:self.workers[slot]=dict(name=name,port=port,started_at=time.monotonic())
            self.event('replica_healthy',slot=slot,reason=reason,port=port)
        except Exception as e:
            self.event('replica_start_failed',slot=slot,reason=reason,error=str(e)[:400]);sh('docker','rm','-f',name,check=False)
            raise
    def remove_worker(self,slot,reason):
        with self.lock:w=self.workers.pop(slot,None)
        if w:
            sh('docker','rm','-f',w['name'],check=False)
            self.event('replica_removed',slot=slot,reason=reason)
    def check_worker(self,slot):
        with self.lock:w=self.workers.get(slot)
        if not w:return False
        return health('http://127.0.0.1:'+str(w['port']),timeout=.65)
    def get_backends(self):
        with self.lock:
            result=[(i,'http://127.0.0.1:'+str(w['port'])) for i,w in self.workers.items()]
            if result:
                self.rr=(self.rr+1)%len(result)
                return result[self.rr:]+result[:self.rr]
            return []
    def note_request(self):
        now=time.monotonic()
        with self.lock:
            self.req_times.append(now)
            self.last_busy=now
            while self.req_times and self.req_times[0]<now-2:self.req_times.popleft()
    def manage_once(self):
        now=time.monotonic()
        with self.lock:
            while self.req_times and self.req_times[0]<now-2:self.req_times.popleft()
            rate=len(self.req_times)/2
            count=len(self.workers)
            idle=now-self.last_busy
            desired=self.desired
            if desired==1 and rate>=self.args.scale_up_rps:
                self.desired=2;self.event('scale_up_decision',rps_2sec=round(rate,1),threshold=self.args.scale_up_rps)
            elif desired==2 and idle>=self.args.scale_down_idle and rate<self.args.scale_up_rps/3:
                self.desired=1;self.event('scale_down_decision',idle_s=round(idle,2))
            desired=self.desired
        # one slot change at a time, outside lock; preflight checks every cycle
        for i in (1,2):
            with self.lock: exists=i in self.workers
            if exists and not self.check_worker(i):
                self.event('replica_detected_unhealthy',slot=i)
                self.remove_worker(i,reason='unhealthy')
                exists=False
            if i<=desired and not exists:
                self.start_worker(i,'automatic_replacement' if i==1 or count>=desired else 'automatic_scale_up')
            if i>desired and exists:
                self.remove_worker(i,reason='automatic_scale_down')
    def manager_loop(self):
        while not self.stopped.is_set():
            try:self.manage_once()
            except Exception as e:self.event('controller_error',error=str(e)[:350])
            self.stopped.wait(.45)
    def cleanup(self):
        self.stopped.set()
        for i in (1,2):
            self.remove_worker(i,'experiment_cleanup')
        # Remove only known names belonging to this experiment; no broad docker prunes.
        for i in (1,2):sh('docker','rm','-f',self.prefix+'-'+str(i),check=False)
        self.env.unlink(missing_ok=True)

class ProxyHandler(BaseHTTPRequestHandler):
    server_version='LH6041-Elasticity-Proxy/1.0'
    def log_message(self,*args):pass
    def do_GET(self):
        c=self.server.controller
        if self.path!='/health':self.send_error(404);return
        with c.lock:data={'ok':True,'role':'test-proxy','replicas':len(c.workers),'desired':c.desired,'version':'v3.1-elasticity-lab'}
        blob=json.dumps(data).encode()
        self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(blob)));self.end_headers();self.wfile.write(blob)
    def do_POST(self):
        if self.path!='/api/sync/order':self.send_error(404);return
        c=self.server.controller;c.note_request()
        body=self.rfile.read(min(int(self.headers.get('Content-Length','0')),100000))
        headers={'Content-Type':'application/json','Authorization':self.headers.get('Authorization','')}
        err=None
        for slot,base in c.get_backends():
            try:
                req=urllib.request.Request(base+'/api/sync/order',data=body,headers=headers,method='POST')
                with urllib.request.urlopen(req,timeout=3) as resp:
                    data=resp.read();status=resp.status
                self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
                return
            except urllib.error.HTTPError as ex:
                # Business/application errors (4xx etc.) are NOT safe to classify as failover.
                data=ex.read();self.send_response(ex.code);self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data);return
            except Exception as ex:
                err=str(ex)[:120];c.event('proxy_backend_transport_error',slot=slot,error=err)
        self.send_response(503);self.send_header('Content-Type','application/json');self.end_headers();self.wfile.write(b'{"error":"no healthy replica"}')

class ProxyServer(ThreadingHTTPServer):
    daemon_threads=True;allow_reuse_address=True
    def __init__(self,addr,controller):super().__init__(addr,ProxyHandler);self.controller=controller

def send_order(base,token,payload,phase):
    b=json.dumps(payload).encode();t=time.perf_counter();status=0;error=''
    try:
        req=urllib.request.Request(base+'/api/sync/order',data=b,method='POST',headers={'Content-Type':'application/json','Authorization':'Bearer '+token})
        with urllib.request.urlopen(req,timeout=7) as resp:status=resp.status;resp.read()
    except urllib.error.HTTPError as e:status=e.code;error='HTTP_'+str(e.code)
    except Exception as e:error=type(e).__name__
    return dict(timestamp_utc=utcnow(),phase=phase,order_id=payload['id'],status=status,success=int(status==200),latency_ms=round((time.perf_counter()-t)*1000,3),error=error)

def traffic(base,token,phase,rps,duration,workers,ctrl,records,kill_after=None):
    start=time.monotonic();end=start+duration;futures=[];kill_id=None
    with ThreadPoolExecutor(max_workers=workers) as ex:
        i=0
        while time.monotonic()<end:
            now=time.monotonic()
            if kill_after is not None and kill_id is None and now-start>=kill_after:
                with ctrl.lock:available=[w for _,w in ctrl.workers.items()]
                if len(available)<2:
                    ctrl.event('kill_skipped_insufficient_replicas',available=len(available))
                else:
                    # Inject failure into exactly one experimental replica while the other stays online.
                    kill_id=available[0]['name'];ctrl.event('injected_replica_failure',victim=kill_id)
                    sh('docker','kill',kill_id,check=False)
            planned=start+i/rps
            delay=planned-time.monotonic()
            if delay>0:time.sleep(min(delay,.06));continue
            i+=1
            if len(futures)>=800:
                break
            futures.append(ex.submit(send_order,base,token,order_payload(),phase))
        for f in as_completed(futures):records.append(f.result())
    return kill_id

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--app-dir',default='/root/pi-cafe-classroom/cloud')
    p.add_argument('--image',default='pi-cafe-classroom-cloud:local')
    p.add_argument('--proxy-port',type=int,default=15110)
    p.add_argument('--backend-port',type=int,default=15121)
    p.add_argument('--memory-mb',type=int,default=150)
    p.add_argument('--scale-up-rps',type=float,default=11)
    p.add_argument('--scale-down-idle',type=float,default=4.0)
    p.add_argument('--out',default=None)
    args=p.parse_args()
    if args.proxy_port in [args.backend_port,args.backend_port+1]:p.error('Port overlap')
    if not 100<=args.memory_mb<=200:p.error('memory-mb must be between 100 and 200')
    if not 4<=args.scale_up_rps<=40:p.error('scale-up-rps must be 4..40')
    if free_mem_mib()<330:
        print('ABORT: host MemAvailable <330 MiB. Do not risk disrupting live service.',file=sys.stderr);sys.exit(2)
    app=Path(args.app_dir)
    missing=[n for n in ['app.py','analytics.py','ai_engine.py','static/index.html'] if not (app/n).is_file()]
    if missing:p.error('Missing cloud V3.1 source: '+str(missing))
    image_plat=sh('docker','image','inspect',args.image,'--format','{{.Os}}/{{.Architecture}}').stdout.strip()
    for port in [args.proxy_port,args.backend_port,args.backend_port+1]:
        sock=socket.socket()
        try:
            sock.bind(('127.0.0.1',port))
        except OSError:p.error('Port '+str(port)+' already in use. Refusing to overwrite live service.')
        finally:sock.close()
    out=Path(args.out or ('runs/elastic_'+datetime.datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')+'_'+secrets.token_hex(2))).resolve()
    if out.exists() and any(out.iterdir()):p.error('Output exists/not empty')
    out.mkdir(parents=True,exist_ok=True)
    ctrl=Orchestrator(args,out,secrets.token_hex(28));records=[];proxy=None;proxy_thr=None;manager=None
    phase_error=None
    try:
        ctrl.start_worker(1,'initial_single_replica')
        proxy=ProxyServer(('127.0.0.1',args.proxy_port),ctrl)
        proxy_thr=threading.Thread(target=proxy.serve_forever,daemon=True);proxy_thr.start()
        manager=threading.Thread(target=ctrl.manager_loop,daemon=True);manager.start()
        base='http://127.0.0.1:'+str(args.proxy_port)
        ctrl.event('baseline_start',target_rps=3)
        traffic(base,ctrl.token,'baseline',3,3,6,ctrl,records)
        ctrl.event('demand_step_start',target_rps=30)
        traffic(base,ctrl.token,'surge',30,8,30,ctrl,records)
        ctrl.event('idle_window_start')
        time.sleep(5.5)
        # Retest scale-up and deliberate failure with active traffic.
        ctrl.event('failure_trial_start',target_rps=25)
        killed=traffic(base,ctrl.token,'failure_under_load',25,7,25,ctrl,records,kill_after=2.7)
        time.sleep(1.5)
        ctrl.event('end_of_measurement',killed=killed or 'not_injected')
    except Exception as e:
        phase_error=str(e)
        ctrl.event('experiment_error',error=phase_error[:400])
    finally:
        ctrl.stopped.set()
        if manager:manager.join(timeout=29)
        if proxy:
            proxy.shutdown();proxy.server_close()
        if proxy_thr:proxy_thr.join(timeout=3)
        ctrl.cleanup()
    with (out/'proxy_requests.csv').open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=['timestamp_utc','phase','order_id','status','success','latency_ms','error']);w.writeheader();w.writerows(records)
    evcols=['timestamp_utc','elapsed_s','event','desired','observed','slot','reason','port','victim','rps_2sec','threshold','idle_s','available','error','killed']
    with (out/'autoscale_events.csv').open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=evcols,extrasaction='ignore');w.writeheader();w.writerows(ctrl.events)
    result={'label':'ACTUAL isolated application-level replica experiment; NOT production auto-scaling, VM auto-scaling, zone HA or deployment',
            'timestamp_utc':utcnow(),'image':args.image,'platform':image_plat,'hostname':socket.gethostname(),
            'host_mem_available_mib_at_end':free_mem_mib(),'proxy_bind':'127.0.0.1:'+str(args.proxy_port),'backends':'127.0.0.1:'+str(args.backend_port)+' and +1',
            'autoscaler_trigger_rps':args.scale_up_rps,'autoscaler_idle_scale_down_s':args.scale_down_idle,
            'phases':{},'events':ctrl.events,'unexpected_error':phase_error,
            'limitations':['All replicas run on one VM; VM outage still causes total service loss.','This is an isolated evaluation controller/proxy, not present in the currently deployed production stack.','Shared SQLite can bottleneck on multi-writer access; report observed HTTP failures without hiding them.','No managed cloud autoscaling group or multi-zone failover.','Load driver, proxy and replicas share the 2-vCPU VM.']}
    for phase in ['baseline','surge','failure_under_load']:
        z=[r for r in records if r['phase']==phase]
        ok=[r['latency_ms'] for r in z if r['success']]
        result['phases'][phase]=dict(requests=len(z),success=len(ok),failures=len(z)-len(ok),success_rate_pct=round(100*len(ok)/max(1,len(z)),2),p95_success_ms=quantile(ok,.95),p99_success_ms=quantile(ok,.99))
    names=[e['event'] for e in ctrl.events]
    result['autoscale_up_observed']='scale_up_decision' in names and any(e['event']=='replica_healthy' and e.get('slot')==2 for e in ctrl.events)
    result['autoscale_down_observed']='scale_down_decision' in names and any(e['event']=='replica_removed' and e.get('reason')=='automatic_scale_down' for e in ctrl.events)
    result['failure_injected']='injected_replica_failure' in names
    result['automatic_recovery_observed']=result['failure_injected'] and any(e['event']=='replica_healthy' and e.get('reason')=='automatic_replacement' and e.get('elapsed_s',0)>=next(k['elapsed_s'] for k in ctrl.events if k['event']=='injected_replica_failure') for e in ctrl.events)
    result['automatic_recovery_time_s']=None
    step=next((e for e in ctrl.events if e['event']=='demand_step_start'),None)
    first2=next((e for e in ctrl.events if e['event']=='replica_healthy' and e.get('slot')==2 and (step is None or e['elapsed_s']>=step['elapsed_s'])),None)
    result['surge_start_to_second_replica_healthy_s']=round(first2['elapsed_s']-step['elapsed_s'],3) if (step and first2) else None
    result['failover_window_first_2s']={'requests':0,'success':0,'errors':0}
    if result['failure_injected']:
        kill=next((e for e in ctrl.events if e['event']=='injected_replica_failure'),None)
        restored=next((e for e in ctrl.events if e['event']=='replica_healthy' and e.get('reason')=='automatic_replacement' and e['elapsed_s']>=kill['elapsed_s']),None)
        if restored:result['automatic_recovery_time_s']=round(restored['elapsed_s']-kill['elapsed_s'],3)
    if result['failure_injected']:
        kill_ts=datetime.datetime.fromisoformat(next(e['timestamp_utc'] for e in ctrl.events if e['event']=='injected_replica_failure'))
        immediate=[r for r in records if r['phase']=='failure_under_load' and 0<=(datetime.datetime.fromisoformat(r['timestamp_utc'])-kill_ts).total_seconds()<=2]
        result['failover_window_first_2s']=dict(requests=len(immediate),success=sum(r['success'] for r in immediate),errors=sum(1-r['success'] for r in immediate),p95_success_ms=quantile([r['latency_ms'] for r in immediate if r['success']],.95))
    db_path=ctrl.db_dir/'ha_test.sqlite3'
    if db_path.exists():
        with sqlite3.connect(db_path) as con:
            saved=con.execute('select count(*) from orders').fetchone()[0]
            dup=con.execute('select count(*) - count(distinct id) from orders').fetchone()[0]
            missing=sum(1 for r in records if r['success'] and not con.execute('select 1 from orders where id=?',(r['order_id'],)).fetchone())
            result.update(db_orders=saved,duplicate_order_ids=dup,missing_accepted_orders=missing)
    else:result.update(db_orders=None,duplicate_order_ids=None,missing_accepted_orders=None)
    (out/'results.json').write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n')
    print('\nRESULT_DIRECTORY:',out,flush=True)
    print('SUMMARY:',json.dumps({k:result[k] for k in ['autoscale_up_observed','autoscale_down_observed','failure_injected','automatic_recovery_observed','automatic_recovery_time_s','missing_accepted_orders','unexpected_error']},ensure_ascii=False),flush=True)
    if phase_error:sys.exit(1)

if __name__=='__main__':main()
