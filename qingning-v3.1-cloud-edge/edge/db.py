"""唯一真实数据源：树莓派 SQLite。所有金额为整数分，菜单版本用于断网补同步。"""
import sqlite3
from pathlib import Path
from contextlib import contextmanager
from menu_seed import MENU

SCHEMA = '''
CREATE TABLE IF NOT EXISTS menu(
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 name TEXT NOT NULL, category TEXT NOT NULL,
 price_cents INTEGER NOT NULL CHECK(price_cents>=0),
 image TEXT NOT NULL, description TEXT NOT NULL,
 badge TEXT NOT NULL DEFAULT '', spicy INTEGER NOT NULL DEFAULT 0,
 available INTEGER NOT NULL DEFAULT 1,
 updated_at TEXT NOT NULL DEFAULT '', version INTEGER NOT NULL DEFAULT 1,
 synced_version INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS orders(
 id TEXT PRIMARY KEY, request_id TEXT NOT NULL UNIQUE,
 table_no INTEGER NOT NULL, source TEXT NOT NULL,
 note TEXT NOT NULL, total_cents INTEGER NOT NULL,
 status TEXT NOT NULL DEFAULT 'queued', created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1,
 synced_version INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS order_items(
 order_id TEXT NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
 menu_id INTEGER NOT NULL, name TEXT NOT NULL, qty INTEGER NOT NULL,
 price_cents INTEGER NOT NULL,
 PRIMARY KEY(order_id,menu_id)
);
CREATE INDEX IF NOT EXISTS ix_pending_orders ON orders(version,synced_version);
CREATE INDEX IF NOT EXISTS ix_pending_menu ON menu(version,synced_version);
CREATE INDEX IF NOT EXISTS ix_orders_created ON orders(created_at);
'''

@contextmanager
def connect(path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    db=sqlite3.connect(str(path),timeout=12)
    db.row_factory=sqlite3.Row
    db.execute('PRAGMA journal_mode=WAL')
    db.execute('PRAGMA foreign_keys=ON')
    db.execute('PRAGMA busy_timeout=12000')
    try:
        with db:yield db
    finally:db.close()

def init(path):
    with connect(path) as db:
        db.executescript(SCHEMA)
        if db.execute('SELECT COUNT(*) FROM menu').fetchone()[0]==0:
            db.executemany('''INSERT INTO menu(id,name,category,price_cents,image,description,badge,spicy)
            VALUES(?,?,?,?,?,?,?,?)''',MENU)

def serialize_order(db,row):
    d=dict(row)
    d['items']=[dict(r) for r in db.execute('SELECT menu_id,name,qty,price_cents FROM order_items WHERE order_id=? ORDER BY menu_id',(row['id'],))]
    d['synced']=d['synced_version']>=d['version']
    return d

def serialize_dish(row):
    d=dict(row)
    d['image_url']='/media/'+d['image'] if d['image'].startswith('up_') else '/static/images/'+d['image']
    d['synced']=d['synced_version']>=d['version']
    return d
