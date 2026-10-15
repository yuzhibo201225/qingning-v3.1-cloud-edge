from __future__ import annotations
import importlib.util, tempfile,threading,time,json,urllib.request,uuid,sys
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path

spec=importlib.util.spec_from_file_location('elastic_lab',str(Path(__file__).parent/'elasticity_failover_experiment.py'))
lab=importlib.util.module_from_spec(spec);sys.modules[spec.name]=lab;spec.loader.exec_module(lab)

def test_quantile():
    assert lab.quantile([1,3,5,7,9],.5)==5
    assert lab.quantile([],.9) is None

def test_autoscaling_controller_decisions_without_docker():
    class Args:
        backend_port=19121;app_dir='/tmp';scale_up_rps=11;scale_down_idle=4
    with tempfile.TemporaryDirectory() as d:
        c=lab.Orchestrator(Args(),Path(d),'fake-test-token')
        def fake_start(i,reason):c.workers[i]={'name':'fake'+str(i),'port':19121+i};c.event('replica_healthy',slot=i,reason=reason)
        def fake_remove(i,reason):c.workers.pop(i,None);c.event('replica_removed',slot=i,reason=reason)
        c.workers[1]={'name':'fake1','port':19122}
        c.start_worker=fake_start;c.remove_worker=fake_remove;c.check_worker=lambda i:True
        for _ in range(30):c.note_request()
        c.manage_once()
        assert c.desired==2 and len(c.workers)==2
        with c.lock:
            c.last_busy-=6;c.req_times.clear()
        c.manage_once()
        assert c.desired==1 and len(c.workers)==1
        assert {'scale_up_decision','scale_down_decision'}<=set(e['event'] for e in c.events)
        c.env.unlink()

class Backend(BaseHTTPRequestHandler):
    def log_message(self,*a):pass
    def do_POST(self):
        body=b'{"accepted":true}'
        self.send_response(200);self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)

def test_proxy_retries_transport_error():
    backend=ThreadingHTTPServer(('127.0.0.1',0),Backend)
    worker=threading.Thread(target=backend.serve_forever,daemon=True);worker.start()
    class Ctrl:
        lock=threading.RLock();desired=2;workers={1:{},2:{}}
        def note_request(self):pass
        def get_backends(self):return [(1,'http://127.0.0.1:1'),(2,'http://127.0.0.1:'+str(backend.server_port))]
        def event(self,*a,**k):pass
    proxy=lab.ProxyServer(('127.0.0.1',0),Ctrl())
    pthr=threading.Thread(target=proxy.serve_forever,daemon=True);pthr.start()
    try:
        p={'id':uuid.uuid4().hex}
        r=lab.send_order('http://127.0.0.1:'+str(proxy.server_port),'test-token',p,'test')
        assert r['status']==200 and r['success']==1
    finally:
        proxy.shutdown();proxy.server_close();backend.shutdown();backend.server_close()
