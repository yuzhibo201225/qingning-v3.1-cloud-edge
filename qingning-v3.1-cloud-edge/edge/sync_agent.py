"""后台同步：订单和菜单/图片都先落树莓派；收到云端相同版本 ACK 才确认。"""
import os,time,json,logging
from pathlib import Path
import requests
from db import connect,init,serialize_order,serialize_dish
logging.basicConfig(level=logging.INFO,format='%(asctime)s [edge-sync] %(message)s')
DB=os.getenv('EDGE_DB','/data/cafe_v3.sqlite3')
ROOT=os.getenv('CLOUD_URL','').rstrip('/')
TOKEN=os.getenv('SYNC_TOKEN','')
POLL=max(3,int(os.getenv('SYNC_INTERVAL','5')))
IMAGE_DIR=Path(os.getenv('MEDIA_DIR','/data/media'))
STATIC_IMAGES=Path(__file__).parent/'static'/'images'

def sync_once(dbpath=DB,base=ROOT,token=TOKEN,media_dir=None):
    if not token or not base.startswith(('http://','https://')):return {'orders':0,'menu':0}
    media_dir=Path(media_dir or IMAGE_DIR)
    headers={'Authorization':'Bearer '+token}
    stats={'orders':0,'menu':0}
    with connect(dbpath) as db:
        menus=[serialize_dish(r) for r in db.execute('SELECT * FROM menu WHERE version>synced_version ORDER BY id LIMIT 15')]
    for dish in menus:
        name=dish['image']
        path=(media_dir/name) if name.startswith('up_') else (STATIC_IMAGES/name)
        try:
            if not path.is_file():raise ValueError('找不到菜品图片 '+name)
            with path.open('rb') as f:
                r=requests.post(base+'/api/sync/menu',headers=headers,
                    data={'menu':json.dumps(dish,ensure_ascii=False)},
                    files={'image':(name,f,'image/webp')},timeout=(3,14))
            r.raise_for_status();ack=r.json()
            if ack.get('menu_id')!=dish['id'] or ack.get('version')!=dish['version'] or not ack.get('accepted'):
                raise ValueError('云端菜单 ACK 不匹配')
            with connect(dbpath) as db:
                db.execute('UPDATE menu SET synced_version=? WHERE id=? AND version=? AND synced_version<?',
                           (dish['version'],dish['id'],dish['version'],dish['version']))
            stats['menu']+=1
        except (requests.RequestException,ValueError,OSError) as e:
            logging.warning('菜单同步失败 id=%s v=%s: %s',dish['id'],dish['version'],str(e)[:150]);break
    with connect(dbpath) as db:
        orders=[serialize_order(db,r) for r in db.execute('SELECT * FROM orders WHERE version>synced_version ORDER BY created_at LIMIT 30')]
    for order in orders:
        try:
            r=requests.post(base+'/api/sync/order',json=order,headers=headers,timeout=(3,8));r.raise_for_status();ack=r.json()
            if ack.get('order_id')!=order['id'] or ack.get('version')!=order['version'] or not ack.get('accepted'):
                raise ValueError('云端订单 ACK 不匹配')
            with connect(dbpath) as db:
                db.execute('UPDATE orders SET synced_version=? WHERE id=? AND version=? AND synced_version<?',
                           (order['version'],order['id'],order['version'],order['version']))
            stats['orders']+=1
        except (requests.RequestException,ValueError) as e:
            logging.warning('订单同步失败 %s: %s',order['id'][:8],str(e)[:150]);break
    try:
        requests.post(base+'/api/sync/heartbeat',headers=headers,json={'at':int(time.time())},timeout=(2,3)).raise_for_status()
    except requests.RequestException:pass
    return stats

if __name__=='__main__':
    init(DB)
    logging.info('离线优先：每 %s 秒尝试同步菜单/图片和订单',POLL)
    while True:
        try:
            res=sync_once()
            if res['orders'] or res['menu']:logging.info('本轮同步完成 %s',res)
        except Exception:logging.exception('同步循环错误，保留本地待同步数据')
        time.sleep(POLL)
