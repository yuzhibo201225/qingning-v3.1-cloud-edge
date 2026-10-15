"""阿里云只读经营看板 + 按版本接收订单和菜单图片（SQLite 持久化）。"""
import os,re,hmac,json,sqlite3,uuid,time
from pathlib import Path
from contextlib import contextmanager
from datetime import datetime,timezone
from urllib.parse import urlsplit
from flask import Flask,request,jsonify,session,send_from_directory
from werkzeug.exceptions import RequestEntityTooLarge
from analytics import get_history, today_beijing
from ai_engine import register_ai

SCHEMA='''
CREATE TABLE IF NOT EXISTS orders(
 id TEXT PRIMARY KEY,table_no INTEGER NOT NULL,source TEXT NOT NULL,note TEXT NOT NULL,
 total_cents INTEGER NOT NULL,status TEXT NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,
 version INTEGER NOT NULL,received_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS order_items(
 order_id TEXT NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
 menu_id INTEGER NOT NULL,name TEXT NOT NULL,qty INTEGER NOT NULL,price_cents INTEGER NOT NULL,
 PRIMARY KEY(order_id,menu_id));
CREATE INDEX IF NOT EXISTS idx_created ON orders(created_at);
CREATE TABLE IF NOT EXISTS menu(
 id INTEGER PRIMARY KEY,name TEXT NOT NULL,category TEXT NOT NULL,price_cents INTEGER NOT NULL,
 description TEXT NOT NULL,badge TEXT NOT NULL,spicy INTEGER NOT NULL,
 available INTEGER NOT NULL,image TEXT NOT NULL,updated_at TEXT NOT NULL,version INTEGER NOT NULL,
 received_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
'''
VALID_STATUS={'queued','preparing','ready','completed','cancelled'}
MAX_PICTURE=700*1024

def verify_webp(data):
    return (12<len(data)<=MAX_PICTURE and data[:4]==b'RIFF' and data[8:12]==b'WEBP' and
        data[12:16] in (b'VP8 ',b'VP8L',b'VP8X') and int.from_bytes(data[4:8],'little')+8==len(data))

@contextmanager
def connect(path):
    Path(path).parent.mkdir(parents=True,exist_ok=True)
    db=sqlite3.connect(str(path),timeout=12)
    db.row_factory=sqlite3.Row
    db.execute('PRAGMA journal_mode=WAL')
    db.execute('PRAGMA foreign_keys=ON')
    db.execute('PRAGMA busy_timeout=12000')
    try:
        with db:yield db
    finally:db.close()

def create_app(database=None,media_dir=None):
    app=Flask(__name__,static_folder='static',static_url_path='/static')
    app.config.update(SECRET_KEY=os.getenv('CLOUD_SESSION_SECRET','testing-only-not-for-production'),
        SESSION_COOKIE_HTTPONLY=True,SESSION_COOKIE_SAMESITE='Lax',JSON_AS_ASCII=False,MAX_CONTENT_LENGTH=1100000)
    path=database or os.getenv('CLOUD_DB','/data/cloud_v3.sqlite3')
    media=Path(media_dir or os.getenv('CLOUD_MEDIA_DIR','/data/media'));media.mkdir(parents=True,exist_ok=True)
    with connect(path) as db:db.executescript(SCHEMA)
    token=os.getenv('SYNC_TOKEN','test-sync-token');pin=os.getenv('DASHBOARD_PIN','135790')
    if os.getenv('DEPLOY_MODE')=='production' and (len(token)<32 or len(pin)<6 or pin=='135790' or len(app.secret_key)<32):
        raise RuntimeError('请生成随机 CLOUD_SESSION_SECRET、SYNC_TOKEN 和 DASHBOARD_PIN')
    attempts={}
    @app.errorhandler(RequestEntityTooLarge)
    def size_error(e):return jsonify(error='图片或请求超过大小限制'),413
    @app.before_request
    def csrf():
        if request.method in ('POST','PATCH','PUT','DELETE') and session.get('admin'):
            origin=request.headers.get('Origin')
            if origin and urlsplit(origin).netloc!=request.host:return jsonify(error='跨站请求被拒绝'),403
    @app.after_request
    def headers(resp):
        resp.headers['X-Content-Type-Options']='nosniff';resp.headers['X-Frame-Options']='DENY'
        resp.headers['Referrer-Policy']='same-origin'
        resp.headers['Content-Security-Policy']="default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'self'"
        if request.path.startswith('/api/'):resp.headers['Cache-Control']='no-store'
        return resp
    def require_sync():return hmac.compare_digest(request.headers.get('Authorization',''),'Bearer '+token)
    def require_admin():return session.get('admin') is True
    @app.get('/health')
    def health():return jsonify(ok=True,role='cloud',version='3.1-ai')
    @app.get('/')
    def home():return send_from_directory('static','index.html')
    @app.get('/media/<name>')
    def image(name):
        if not require_admin():return jsonify(error='未登录'),401
        if not re.fullmatch(r'm_[0-9]+_[0-9]+\.webp',name):return jsonify(error='不存在'),404
        return send_from_directory(media,name,mimetype='image/webp')
    @app.post('/api/login')
    def login():
        ip=request.remote_addr or 'unknown';t=time.monotonic()
        attempts[ip]=[x for x in attempts.get(ip,[]) if t-x<300]
        if len(attempts[ip])>=8:return jsonify(error='尝试次数过多，请五分钟后重试'),429
        supplied=str((request.get_json(silent=True) or {}).get('pin',''))
        if not hmac.compare_digest(supplied,pin):attempts[ip].append(t);return jsonify(error='看板口令错误'),401
        attempts.pop(ip,None);session.clear();session['admin']=True
        return jsonify(ok=True)
    @app.get('/api/me')
    def me():return jsonify(ok=require_admin())
    @app.post('/api/logout')
    def logout():session.clear();return jsonify(ok=True)
    @app.post('/api/sync/heartbeat')
    def heartbeat():
        if not require_sync():return jsonify(error='云同步鉴权失败'),401
        with connect(path) as db:
            db.execute("INSERT INTO meta(key,value) VALUES('last_heartbeat',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (datetime.now(timezone.utc).isoformat(timespec='seconds'),))
        return jsonify(ok=True)
    @app.post('/api/sync/menu')
    def ingest_menu():
        if not require_sync():return jsonify(error='云同步鉴权失败'),401
        try:
            d=json.loads(request.form['menu']);pic=request.files['image'].read(MAX_PICTURE+1)
            mid=d['id'];v=d['version']
            if type(mid)!=int or not 1<=mid<1000000 or type(v)!=int or not 1<=v<1000000:raise ValueError()
            if not verify_webp(pic):raise ValueError()
            if not isinstance(d['name'],str) or not 1<=len(d['name'])<=40:raise ValueError()
            if not isinstance(d['category'],str) or not 1<=len(d['category'])<=24:raise ValueError()
            if not isinstance(d['description'],str) or len(d['description'])>100:raise ValueError()
            if not isinstance(d['badge'],str) or len(d['badge'])>20:raise ValueError()
            if type(d['price_cents'])!=int or not 100<=d['price_cents']<=100000:raise ValueError()
            if d['available'] not in (0,1) or d['spicy'] not in (0,1):raise ValueError()
            if not isinstance(d['updated_at'],str) or len(d['updated_at'])>45:raise ValueError()
        except (KeyError,ValueError,TypeError,UnicodeDecodeError,AttributeError):return jsonify(error='菜品或图片格式无效'),400
        filename=f'm_{mid}_{v}.webp'
        with connect(path) as db:
            db.execute('BEGIN IMMEDIATE')
            old=db.execute('SELECT version FROM menu WHERE id=?',(mid,)).fetchone()
            if old is None or v>old['version']:
                temp=media/(filename+'.'+uuid.uuid4().hex+'.tmp')
                try:
                    with temp.open('wb') as file:
                        file.write(pic);file.flush();os.fsync(file.fileno())
                    temp.replace(media/filename)
                    db.execute('''INSERT INTO menu(id,name,category,price_cents,description,badge,spicy,available,image,updated_at,version,received_at)
                        VALUES(?,?,?,?,?,?,?,?,?,?,?,datetime('now'))
                        ON CONFLICT(id) DO UPDATE SET name=excluded.name,category=excluded.category,price_cents=excluded.price_cents,
                        description=excluded.description,badge=excluded.badge,spicy=excluded.spicy,available=excluded.available,
                        image=excluded.image,updated_at=excluded.updated_at,version=excluded.version,received_at=excluded.received_at''',
                        (mid,d['name'],d['category'],d['price_cents'],d['description'],d['badge'],int(d['spicy']),int(d['available']),filename,d['updated_at'],v))
                finally:temp.unlink(missing_ok=True)
        return jsonify(accepted=True,menu_id=mid,version=v)
    @app.post('/api/sync/order')
    def ingest_order():
        if not require_sync():return jsonify(error='云同步鉴权失败'),401
        d=request.get_json(silent=True)
        if not isinstance(d,dict):return jsonify(error='订单 JSON 无效'),400
        try:
            oid=d['id'];v=d['version'];items=d['items']
            if not isinstance(oid,str) or not re.fullmatch('[0-9a-f]{32}',oid):raise ValueError()
            if type(v)!=int or not 1<=v<1000000:raise ValueError()
            if d['status'] not in VALID_STATUS or type(d['total_cents'])!=int or not 0<=d['total_cents']<=2000000:raise ValueError()
            if type(d['table_no'])!=int or not 1<=d['table_no']<=99:raise ValueError()
            if d['source'] not in ('customer','cashier'):raise ValueError()
            if not isinstance(d['note'],str) or len(d['note'])>100:raise ValueError()
            if not isinstance(items,list) or not 1<=len(items)<=20:raise ValueError()
            for x in items:
                if not isinstance(x,dict) or type(x['menu_id'])!=int or type(x['qty'])!=int or type(x['price_cents'])!=int:raise ValueError()
                if not 1<=x['qty']<=20 or not 100<=x['price_cents']<=100000 or not isinstance(x['name'],str) or len(x['name'])>40:raise ValueError()
            if sum(x['price_cents']*x['qty'] for x in items)!=d['total_cents']:raise ValueError()
            for key in ('created_at','updated_at'):
                if not isinstance(d[key],str) or len(d[key])>45:raise ValueError()
                datetime.fromisoformat(d[key])
        except (ValueError,TypeError,KeyError):return jsonify(error='订单结构无效'),400
        with connect(path) as db:
            db.execute('BEGIN IMMEDIATE')
            old=db.execute('SELECT version FROM orders WHERE id=?',(oid,)).fetchone()
            if old is None or v>old['version']:
                db.execute('''INSERT INTO orders(id,table_no,source,note,total_cents,status,created_at,updated_at,version,received_at)
                    VALUES(?,?,?,?,?,?,?,?,?,datetime('now'))
                    ON CONFLICT(id) DO UPDATE SET table_no=excluded.table_no,source=excluded.source,note=excluded.note,
                    total_cents=excluded.total_cents,status=excluded.status,updated_at=excluded.updated_at,version=excluded.version,received_at=excluded.received_at''',
                    (oid,d['table_no'],d['source'],d['note'],d['total_cents'],d['status'],d['created_at'],d['updated_at'],v))
                db.execute('DELETE FROM order_items WHERE order_id=?',(oid,))
                db.executemany('INSERT INTO order_items(order_id,menu_id,name,qty,price_cents) VALUES(?,?,?,?,?)',
                    [(oid,i['menu_id'],i['name'],i['qty'],i['price_cents']) for i in items])
        return jsonify(accepted=True,order_id=oid,version=v)
    @app.get('/api/stats')
    def stats():
        if not require_admin():return jsonify(error='请先登录'),401
        with connect(path) as db:
            totals=db.execute("SELECT COUNT(*) n,COALESCE(SUM(total_cents),0) amount FROM orders WHERE status!='cancelled'").fetchone()
            byhour=[dict(r) for r in db.execute("SELECT substr(created_at,12,2) hour,COUNT(*) count FROM orders WHERE status!='cancelled' GROUP BY substr(created_at,12,2) ORDER BY hour")]
            top=[dict(r) for r in db.execute("SELECT i.name,SUM(i.qty) qty FROM order_items i JOIN orders o ON i.order_id=o.id WHERE o.status!='cancelled' GROUP BY i.menu_id,i.name ORDER BY qty DESC LIMIT 10")]
            daily=[dict(r) for r in db.execute("SELECT substr(created_at,1,10) day,COUNT(*) count,SUM(total_cents) amount_cents FROM orders WHERE status!='cancelled' GROUP BY substr(created_at,1,10) ORDER BY day DESC LIMIT 7")]
            states=[dict(r) for r in db.execute('SELECT status,COUNT(*) n FROM orders GROUP BY status')]
            orders=[]
            for r in db.execute('SELECT * FROM orders ORDER BY created_at DESC LIMIT 100'):
                o=dict(r);o['items']=[dict(i) for i in db.execute('SELECT * FROM order_items WHERE order_id=?',(o['id'],))];orders.append(o)
            menus=[dict(r) for r in db.execute('SELECT * FROM menu ORDER BY id')]
            last=db.execute("SELECT value FROM meta WHERE key='last_heartbeat'").fetchone()
        for m in menus:m['image_url']='/media/'+m['image']
        return jsonify(order_count=totals['n'],order_amount_cents=totals['amount'],by_hour=byhour,
            top=top,by_day=daily,by_status=states,orders=orders,menu=menus,
            last_heartbeat=last['value'] if last else None)
    @app.get('/api/history')
    def history():
        if not require_admin():return jsonify(error='请先登录'),401
        today=today_beijing()
        end=request.args.get('end',today.isoformat())
        start=request.args.get('start',(today-__import__('datetime').timedelta(days=29)).isoformat())
        group=request.args.get('group','day')
        try:
            return jsonify(get_history(connect,path,start,end,group))
        except (ValueError,TypeError):
            return jsonify(error='日期格式错误，或查询范围超过366天'),400
    register_ai(app,connect,path,require_admin)
    return app

app=create_app()
