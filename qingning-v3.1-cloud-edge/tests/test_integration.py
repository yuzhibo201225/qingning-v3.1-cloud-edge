"""API integration tests run on any dev PC with requirements installed.
python -m pip install -r edge/requirements.txt pytest
python -m pytest tests -q
"""
import io, os, sys, uuid, importlib.util
from pathlib import Path
import pytest

ROOT=Path(__file__).resolve().parents[1]
EDGE=ROOT/'edge';CLOUD=ROOT/'cloud'
sys.path.insert(0,str(EDGE))
sys.path.insert(0,str(CLOUD))

def load_module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

@pytest.fixture
def pair(tmp_path,monkeypatch):
    monkeypatch.setenv('EDGE_DB',str(tmp_path/'edge_boot.sqlite3'))
    monkeypatch.setenv('CLOUD_DB',str(tmp_path/'cloud_boot.sqlite3'))
    monkeypatch.setenv('MEDIA_DIR',str(tmp_path/'edge_media'))
    monkeypatch.setenv('CLOUD_MEDIA_DIR',str(tmp_path/'cloud_media'))
    monkeypatch.setenv('STAFF_PIN','88123456')
    monkeypatch.setenv('DASHBOARD_PIN','99876543')
    monkeypatch.setenv('SYNC_TOKEN','z'*44)
    monkeypatch.setenv('SESSION_SECRET','e'*64)
    monkeypatch.setenv('CLOUD_SESSION_SECRET','c'*64)
    monkeypatch.setenv('DEPLOY_MODE','test')
    edge=load_module('cafe_v3_edge_test',EDGE/'app.py')
    cloud=load_module('cafe_v3_cloud_test',CLOUD/'app.py')
    ea=edge.create_app(str(tmp_path/'edge.sqlite3'),str(tmp_path/'edge_media'))
    ca=cloud.create_app(str(tmp_path/'cloud.sqlite3'),str(tmp_path/'cloud_media'))
    ea.testing=True;ca.testing=True
    return ea,ca,edge,cloud

def create_order(c,rid=None,price=2490,mid=1,qty=2):
    return c.post('/api/orders',json={'table_no':2,'source':'customer','note':'少辣',
        'request_id':rid or str(uuid.uuid4()),'items':[{'id':mid,'qty':qty,'price_cents':price}]})

def login_staff(client):
    assert client.post('/api/login',json={'pin':'88123456'}).status_code==200

def test_create_order_idempotence_and_history(pair):
    ea,ca,edge,cloud=pair;x=ea.test_client();rid=str(uuid.uuid4())
    created=create_order(x,rid)
    assert created.status_code==201
    order=created.json['order']
    assert order['total_cents']==4980 and not order['synced']
    assert create_order(x,rid).json['order']['id']==order['id']
    assert x.get('/api/staff/orders').status_code==401
    login_staff(x)
    assert x.patch('/api/staff/menu/1',json={'price_cents':2590}).status_code==200
    assert create_order(ea.test_client(),price=2490).status_code==409
    newest=create_order(ea.test_client(),price=2590)
    assert newest.status_code==201 and newest.json['order']['total_cents']==5180
    old=x.get('/api/staff/orders').json['orders'][-1]
    assert old['total_cents']==4980 and old['items'][0]['price_cents']==2490
    assert ea.test_client().get('/api/menu').json['menu'][0]['price_cents']==2590

def test_new_dish_upload_visibility_repricing_and_disabling(pair):
    ea,ca,e,c=pair;x=ea.test_client();login_staff(x)
    photo=(EDGE/'static/images/kungpao.webp').read_bytes()
    result=x.post('/api/staff/menu',data={'name':'新菜','category':'新分类','price_cents':'3500',
        'description':'现炒','badge':'上新','spicy':'false','available':'true','image':(io.BytesIO(photo),'dish.webp')},content_type='multipart/form-data')
    assert result.status_code==201,result.json
    row=result.json['menu_item'];mid=row['id'];assert mid>=13
    url=row['image_url'];assert x.get(url).status_code==200
    guest=ea.test_client();assert any(m['id']==mid for m in guest.get('/api/menu').json['menu'])
    oldrev=guest.get('/api/menu-revision').json['revision']
    change=x.patch(f'/api/staff/menu/{mid}',json={'price_cents':3700,'name':'新菜特选'})
    assert change.status_code==200
    assert guest.get('/api/menu-revision').json['revision']>oldrev
    assert create_order(guest,mid=mid,price=3500).status_code==409
    assert create_order(guest,mid=mid,price=3700,qty=1).status_code==201
    assert x.patch(f'/api/staff/menu/{mid}',json={'available':False}).status_code==200
    assert not any(m['id']==mid for m in guest.get('/api/menu').json['menu'])
    assert create_order(guest,mid=mid,price=3700).status_code==409
    second=x.post(f'/api/staff/menu/{mid}/image',data={'image':(io.BytesIO(photo),'updated.webp')},content_type='multipart/form-data')
    assert second.status_code==200 and second.json['menu_item']['image']!=row['image']

def test_cloud_orders_and_menu_versioned_ack(pair):
    ea,ca,e,c=pair;guest=ea.test_client();admin=ea.test_client();cloud=ca.test_client();login_staff(admin)
    order=create_order(guest).json['order']
    assert cloud.post('/api/sync/order',json=order).status_code==401
    headers={'Authorization':'Bearer '+'z'*44}
    assert cloud.post('/api/sync/order',json=order,headers=headers).status_code==200
    assert cloud.post('/api/sync/order',json=order,headers=headers).status_code==200
    admin.patch('/api/staff/orders/'+order['id']+'/status',json={'status':'preparing'})
    updated=admin.get('/api/staff/orders').json['orders'][0]
    assert updated['version']==2
    assert cloud.post('/api/sync/order',json=updated,headers=headers).status_code==200
    assert cloud.post('/api/login',json={'pin':'99876543'}).status_code==200
    stats=cloud.get('/api/stats').json
    assert stats['order_count']==1 and stats['orders'][0]['status']=='preparing'
    dish=admin.get('/api/menu').json['menu'][0]
    photo=(EDGE/'static/images/kungpao.webp').read_bytes()
    data={'menu':__import__('json').dumps(dish),'image':(io.BytesIO(photo),'kungpao.webp')}
    res=cloud.post('/api/sync/menu',headers=headers,data=data,content_type='multipart/form-data')
    assert res.status_code==200,res.json
    assert len(cloud.get('/api/stats').json['menu'])==1

def test_pages_qr_and_assets(pair):
    ea,ca,e,c=pair;x=ea.test_client()
    for page in ['/','/cashier','/kitchen','/dashboard','/manage','/qr','/login']:
        assert x.get(page).status_code==200
    assert x.get('/api/qr.svg?table=2').status_code==401
    login_staff(x)
    assert b'<svg' in x.get('/api/qr.svg?table=2').data
    for dish in x.get('/api/menu').json['menu']:
        assert x.get(dish['image_url']).status_code==200
