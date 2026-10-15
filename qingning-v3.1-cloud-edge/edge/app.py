"""青柠食光 V3：树莓派本地主系统（Flask/SQLite，无在线 CDN 依赖）。"""
import os,re,uuid,hmac,time
from datetime import datetime,timezone,timedelta
from functools import wraps
from pathlib import Path
from urllib.parse import urlsplit
from flask import Flask,request,jsonify,send_from_directory,session,make_response
from werkzeug.exceptions import RequestEntityTooLarge
from db import connect,init,serialize_order,serialize_dish

TZ=timezone(timedelta(hours=8))
def now():return datetime.now(TZ).isoformat(timespec='seconds')
TRANSITIONS={'queued':{'preparing','cancelled'},'preparing':{'ready','cancelled'},'ready':{'completed'},'completed':set(),'cancelled':set()}
MAX_PICTURE=700*1024

def verify_webp(data):
    return (12<len(data)<=MAX_PICTURE and data[:4]==b'RIFF' and data[8:12]==b'WEBP' and
            data[12:16] in (b'VP8 ',b'VP8L',b'VP8X') and int.from_bytes(data[4:8],'little')+8==len(data))

def create_app(database=None,media_dir=None):
    app=Flask(__name__,static_folder='static',static_url_path='/static')
    app.config.update(SECRET_KEY=os.getenv('SESSION_SECRET','testing-only-not-for-production'),
        SESSION_COOKIE_HTTPONLY=True,SESSION_COOKIE_SAMESITE='Lax',MAX_CONTENT_LENGTH=1100000,JSON_AS_ASCII=False)
    path=database or os.getenv('EDGE_DB','/data/cafe_v3.sqlite3')
    media=Path(media_dir or os.getenv('MEDIA_DIR','/data/media'))
    media.mkdir(parents=True,exist_ok=True)
    app.config['DB_PATH']=path
    init(path)
    pin=os.getenv('STAFF_PIN','246810')
    if os.getenv('DEPLOY_MODE')=='production' and (len(pin)<6 or pin=='246810' or len(app.secret_key)<32):
        raise RuntimeError('请先生成 .env 中的 STAFF_PIN 和 SESSION_SECRET')
    attempts={}
    def conn():return connect(path)
    def staff_only(f):
        @wraps(f)
        def wrapped(*a,**kw):
            if session.get('staff') is not True:return jsonify(error='请先登录商家端'),401
            return f(*a,**kw)
        return wrapped
    @app.errorhandler(RequestEntityTooLarge)
    def too_large(e):return jsonify(error='上传内容过大；图片请压缩至 700 KB 内'),413
    @app.after_request
    def headers(resp):
        resp.headers['X-Content-Type-Options']='nosniff'
        resp.headers['X-Frame-Options']='SAMEORIGIN'
        resp.headers['Referrer-Policy']='same-origin'
        resp.headers['Content-Security-Policy']="default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self'; img-src 'self' data: blob:; connect-src 'self'; object-src 'none'; base-uri 'self'"
        if request.path.startswith('/api/'):resp.headers['Cache-Control']='no-store'
        return resp
    @app.before_request
    def origin_check():
        if request.method in ('POST','PATCH','PUT','DELETE') and session.get('staff'):
            origin=request.headers.get('Origin')
            if origin and urlsplit(origin).netloc!=request.host:
                return jsonify(error='跨站修改请求已拒绝'),403
    @app.get('/health')
    def health():return jsonify(ok=True,role='edge',version='3.0')
    @app.get('/')
    def home():return send_from_directory('static','index.html')
    for route,filename in [('/cashier','cashier.html'),('/dashboard','dashboard.html'),('/qr','qr.html'),('/login','login.html'),('/manage','manage.html')]:
        app.add_url_rule(route,endpoint='page_'+filename,view_func=lambda name=filename:send_from_directory('static',name))
    @app.get('/media/<name>')
    def media_file(name):
        if not re.fullmatch(r'up_[0-9a-f]{32}\.webp',name):return jsonify(error='文件不存在'),404
        return send_from_directory(media,name,mimetype='image/webp')
    @app.get('/api/menu')
    def menu():
        with conn() as db:rows=[serialize_dish(r) for r in db.execute('SELECT * FROM menu ORDER BY id')]
        if not session.get('staff'):rows=[r for r in rows if r['available']]
        with conn() as db:revision=db.execute('SELECT COALESCE(SUM(version),0) FROM menu').fetchone()[0]
        return jsonify(menu=rows,revision=revision)
    @app.get('/api/menu-revision')
    def menu_revision():
        with conn() as db:r=db.execute('SELECT COALESCE(SUM(version),0) rev,COUNT(*) count FROM menu').fetchone()
        return jsonify(revision=r['rev'],count=r['count'])
    @app.post('/api/orders')
    def add_order():
        d=request.get_json(silent=True)
        if not isinstance(d,dict):return jsonify(error='请提交 JSON 订单'),400
        try:
            table=d['table_no']
            if type(table)!=int or not 1<=table<=99:raise ValueError('桌号必须是 1–99')
            rid=str(uuid.UUID(str(d['request_id'])))
            source=d.get('source','customer')
            if source not in ('customer','cashier'):raise ValueError('订单来源不合法')
            if source=='cashier' and not session.get('staff'):return jsonify(error='收银台需要登录'),401
            note=d.get('note','')
            if not isinstance(note,str) or len(note)>100:raise ValueError('备注过长')
            items=d['items']
            if not isinstance(items,list) or not 1<=len(items)<=20:raise ValueError('每单需要 1–20 种菜品')
            counts={};prices={}
            for item in items:
                if not isinstance(item,dict):raise ValueError('菜品数据有误')
                mid=item['id'];qty=item['qty'];expected=item['price_cents']
                if type(mid)!=int or type(qty)!=int or type(expected)!=int or not 1<=qty<=20:raise ValueError('菜品数量或单价无效')
                counts[mid]=counts.get(mid,0)+qty
                if mid in prices and prices[mid]!=expected:raise ValueError('同一菜品价格矛盾')
                prices[mid]=expected
            if any(q>20 for q in counts.values()):raise ValueError('每种菜品最多20份')
        except (ValueError,KeyError,TypeError,AttributeError) as e:
            return jsonify(error=str(e) if str(e) else '订单字段缺失'),400
        with conn() as db:
            db.execute('BEGIN IMMEDIATE')
            previous=db.execute('SELECT * FROM orders WHERE request_id=?',(rid,)).fetchone()
            if previous:return jsonify(order=serialize_order(db,previous),duplicate=True),200
            dishes={r['id']:r for r in db.execute('SELECT * FROM menu WHERE available=1')}
            if any(mid not in dishes for mid in counts):return jsonify(error='菜品已下架或不存在，请刷新菜单'),409
            if any(prices[mid]!=dishes[mid]['price_cents'] for mid in counts):return jsonify(error='有菜品价格已经更新，请刷新菜单并重新确认订单'),409
            total=sum(dishes[mid]['price_cents']*qty for mid,qty in counts.items())
            if total>2000000:return jsonify(error='订单总价超过限制'),400
            oid=uuid.uuid4().hex;t=now()
            db.execute('INSERT INTO orders(id,request_id,table_no,source,note,total_cents,status,created_at,updated_at,version,synced_version) VALUES(?,?,?,?,?,?,?,?,?,1,0)',
                (oid,rid,table,source,note.strip(),total,'queued',t,t))
            for mid,qty in counts.items():
                dish=dishes[mid]
                db.execute('INSERT INTO order_items(order_id,menu_id,name,qty,price_cents) VALUES(?,?,?,?,?)',
                    (oid,mid,dish['name'],qty,dish['price_cents']))
            out=serialize_order(db,db.execute('SELECT * FROM orders WHERE id=?',(oid,)).fetchone())
        return jsonify(order=out,duplicate=False),201
    @app.get('/api/orders/<oid>')
    def order_detail(oid):
        if not re.fullmatch(r'[0-9a-f]{32}',oid):return jsonify(error='订单不存在'),404
        with conn() as db:
            row=db.execute('SELECT * FROM orders WHERE id=?',(oid,)).fetchone()
            return jsonify(order=serialize_order(db,row)) if row else (jsonify(error='订单不存在'),404)
    @app.post('/api/login')
    def login():
        ip=request.remote_addr or 'unknown';t=time.monotonic()
        attempts[ip]=[x for x in attempts.get(ip,[]) if t-x<300]
        if len(attempts[ip])>=8:return jsonify(error='失败次数过多，请五分钟后再试'),429
        supplied=str((request.get_json(silent=True) or {}).get('pin',''))
        if not hmac.compare_digest(supplied,pin):
            attempts[ip].append(t);return jsonify(error='店员口令错误'),401
        attempts.pop(ip,None);session.clear();session['staff']=True
        return jsonify(ok=True)
    @app.post('/api/logout')
    def logout():session.clear();return jsonify(ok=True)
    @app.get('/api/staff/me')
    @staff_only
    def who():return jsonify(ok=True)
    @app.get('/api/staff/orders')
    @staff_only
    def orders():
        with conn() as db:
            rows=db.execute('SELECT * FROM orders ORDER BY created_at DESC LIMIT 150').fetchall()
            return jsonify(orders=[serialize_order(db,r) for r in rows])
    @app.patch('/api/staff/orders/<oid>/status')
    @staff_only
    def status(oid):
        value=(request.get_json(silent=True) or {}).get('status')
        with conn() as db:
            db.execute('BEGIN IMMEDIATE')
            old=db.execute('SELECT * FROM orders WHERE id=?',(oid,)).fetchone()
            if not old:return jsonify(error='订单不存在'),404
            if value not in TRANSITIONS.get(old['status'],set()):return jsonify(error='订单状态转换不允许'),409
            db.execute('UPDATE orders SET status=?,updated_at=?,version=version+1 WHERE id=?',(value,now(),oid))
            return jsonify(order=serialize_order(db,db.execute('SELECT * FROM orders WHERE id=?',(oid,)).fetchone()))
    def validate_dish(d,existing=None):
        base=dict(existing) if existing else {}
        for key,limit in [('name',40),('category',24),('description',100),('badge',20)]:
            if key in d:
                value=d[key]
                if not isinstance(value,str) or len(value.strip())>limit or (key in ('name','category') and not value.strip()):
                    raise ValueError(key+' 必须为有效文字，长度不超过 '+str(limit))
                base[key]=value.strip()
        for key in ('available','spicy'):
            if key in d:
                if type(d[key])!=bool:raise ValueError(key+' 必须为 true/false')
                base[key]=int(d[key])
        if 'price_cents' in d:
            p=d['price_cents']
            if type(p)!=int or not 100<=p<=100000:raise ValueError('价格必须在 1–1000 元之间')
            base['price_cents']=p
        if not existing and not all(base.get(k) is not None for k in ('name','category','price_cents')):
            raise ValueError('必须填写菜名、分类和价格')
        return base
    def extract_picture():
        file=request.files.get('image')
        if not file or not file.filename:raise ValueError('请选择一张菜品图片')
        raw=file.read(MAX_PICTURE+1)
        if not verify_webp(raw):raise ValueError('图片请使用网页自动压缩的 WebP，大小不超过 700 KB')
        name='up_'+uuid.uuid4().hex+'.webp'
        temp=media/(name+'.tmp');final=media/name
        with temp.open('wb') as out:
            out.write(raw);out.flush();os.fsync(out.fileno())
        temp.replace(final)
        return name
    @app.post('/api/staff/menu')
    @staff_only
    def create_dish():
        try:
            fields={k:request.form[k] for k in ('name','category','description','badge') if k in request.form}
            fields['price_cents']=int(request.form.get('price_cents',''))
            fields['spicy']=request.form.get('spicy','false')=='true'
            fields['available']=request.form.get('available','true')=='true'
            d=validate_dish(fields);pic=extract_picture();t=now()
        except (ValueError,TypeError) as e:return jsonify(error=str(e)),400
        try:
            with conn() as db:
                cur=db.execute('INSERT INTO menu(name,category,price_cents,image,description,badge,spicy,available,updated_at,version,synced_version) VALUES(?,?,?,?,?,?,?,?,?,1,0)',
                    (d['name'],d['category'],d['price_cents'],pic,d.get('description',''),d.get('badge',''),d.get('spicy',0),d.get('available',1),t))
                row=db.execute('SELECT * FROM menu WHERE id=?',(cur.lastrowid,)).fetchone()
                return jsonify(menu_item=serialize_dish(row)),201
        except Exception:
            (media/pic).unlink(missing_ok=True);raise
    @app.patch('/api/staff/menu/<int:mid>')
    @staff_only
    def edit_dish(mid):
        payload=request.get_json(silent=True)
        if not isinstance(payload,dict) or not payload:return jsonify(error='未提交修改内容'),400
        if any(k not in ('name','category','description','badge','price_cents','available','spicy') for k in payload):
            return jsonify(error='包含不允许修改的字段'),400
        with conn() as db:
            db.execute('BEGIN IMMEDIATE')
            old=db.execute('SELECT * FROM menu WHERE id=?',(mid,)).fetchone()
            if not old:return jsonify(error='菜品不存在'),404
            try:valid=validate_dish(payload,old)
            except ValueError as e:return jsonify(error=str(e)),400
            if all(valid.get(k)==old[k] for k in payload):return jsonify(menu_item=serialize_dish(old))
            args=[valid[k] for k in payload]
            db.execute('UPDATE menu SET '+','.join(k+'=?' for k in payload)+',updated_at=?,version=version+1 WHERE id=?',
                (*args,now(),mid))
            row=db.execute('SELECT * FROM menu WHERE id=?',(mid,)).fetchone()
            return jsonify(menu_item=serialize_dish(row))
    @app.post('/api/staff/menu/<int:mid>/image')
    @staff_only
    def update_picture(mid):
        with conn() as db:
            if not db.execute('SELECT id FROM menu WHERE id=?',(mid,)).fetchone():return jsonify(error='菜品不存在'),404
        try:name=extract_picture()
        except ValueError as e:return jsonify(error=str(e)),400
        with conn() as db:
            db.execute('UPDATE menu SET image=?,updated_at=?,version=version+1 WHERE id=?',(name,now(),mid))
            row=db.execute('SELECT * FROM menu WHERE id=?',(mid,)).fetchone()
            return jsonify(menu_item=serialize_dish(row))
    @app.get('/api/staff/stats')
    @staff_only
    def stats():
        with conn() as db:
            totals=db.execute("SELECT COUNT(*) n,COALESCE(SUM(total_cents),0) amount FROM orders WHERE status!='cancelled'").fetchone()
            byhour=[dict(r) for r in db.execute("SELECT substr(created_at,12,2) hour,COUNT(*) count FROM orders WHERE status!='cancelled' GROUP BY substr(created_at,12,2) ORDER BY hour")]
            byday=[dict(r) for r in db.execute("SELECT substr(created_at,1,10) day,COUNT(*) count,SUM(total_cents) amount_cents FROM orders WHERE status!='cancelled' GROUP BY substr(created_at,1,10) ORDER BY day DESC LIMIT 7")]
            top=[dict(r) for r in db.execute("SELECT i.name,SUM(i.qty) qty FROM order_items i JOIN orders o ON i.order_id=o.id WHERE o.status!='cancelled' GROUP BY i.menu_id,i.name ORDER BY qty DESC LIMIT 8")]
            pending=db.execute('SELECT COUNT(*) FROM orders WHERE version>synced_version').fetchone()[0]
            pending_menu=db.execute('SELECT COUNT(*) FROM menu WHERE version>synced_version').fetchone()[0]
            states=[dict(r) for r in db.execute('SELECT status,COUNT(*) n FROM orders GROUP BY status')]
        return jsonify(order_count=totals['n'],order_amount_cents=totals['amount'],by_hour=byhour,by_day=byday,top=top,pending_sync=pending,pending_menu=pending_menu,by_status=states)
    @app.get('/api/qr.svg')
    @staff_only
    def qr():
        try:table=int(request.args.get('table','1'))
        except ValueError:return jsonify(error='桌号错误'),400
        if not 1<=table<=99:return jsonify(error='桌号错误'),400
        import segno,io
        url=os.getenv('PUBLIC_EDGE_URL','http://EDGE_LOCAL_IP:18080').rstrip('/')+'/?table='+str(table)
        out=io.BytesIO();segno.make(url,error='m').save(out,kind='svg',scale=6,dark='#184d3b',light='#ffffff',border=2)
        response=make_response(out.getvalue());response.headers['Content-Type']='image/svg+xml';return response
    @app.get('/api/site')
    def site():return jsonify(title=os.getenv('SHOP_NAME','青柠食光'),public_url=os.getenv('PUBLIC_EDGE_URL','http://EDGE_LOCAL_IP:18080'))
    return app

app=create_app()
