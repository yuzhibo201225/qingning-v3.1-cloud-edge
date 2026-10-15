"""Offline tests: python3 -m unittest discover -s tests -v"""
import sys, unittest, sqlite3, tempfile
from pathlib import Path
from contextlib import contextmanager
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'cloud'))
from analytics import get_history,period_bounds

@contextmanager
def connect(path):
    db=sqlite3.connect(path)
    db.row_factory=sqlite3.Row
    try:
        with db: yield db
    finally: db.close()

class TestHistory(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.db=str(Path(self.tmp.name)/'test.sqlite3')
        with connect(self.db) as d:
            d.executescript('''CREATE TABLE orders(id TEXT PRIMARY KEY,created_at TEXT,status TEXT,source TEXT,total_cents INTEGER);
                CREATE TABLE order_items(order_id TEXT,menu_id INTEGER,name TEXT,qty INTEGER,price_cents INTEGER);''')
            d.executemany('INSERT INTO orders VALUES(?,?,?,?,?)',[
                ('a','2026-10-11T11:45:00+08:00','completed','customer',2800),
                ('b','2026-10-12T12:30:00+08:00','queued','cashier',8000),
                ('c','2026-10-12T20:30:00+08:00','cancelled','customer',1000),
                ('d','2026-10-13T12:00:00+08:00','queued','customer',4000)])
            d.executemany('INSERT INTO order_items VALUES(?,?,?,?,?)',[
                ('a',1,'可乐',2,1400),('b',2,'米饭',4,2000),('c',1,'可乐',1,1000),('d',2,'米饭',2,2000)])
    def tearDown(self):self.tmp.cleanup()
    def test_daily(self):
        r=get_history(connect,self.db,'2026-10-11','2026-10-13','day')
        self.assertEqual(r['summary']['order_count'],3)
        self.assertEqual(r['summary']['cancelled'],1)
        self.assertEqual(r['summary']['amount_cents'],14800)
        self.assertEqual(r['summary']['items_sold'],8)
        self.assertEqual([x['count'] for x in r['buckets']],[1,1,1])
        self.assertEqual(r['by_hour'][12]['count'],2)
        self.assertEqual(r['top_dishes'][0]['qty'],6)
        self.assertEqual(r['by_weekday'][0]['count'],1)
    def test_week_boundary(self):
        r=get_history(connect,self.db,'2026-10-11','2026-10-13','week')
        self.assertEqual([x['period'] for x in r['buckets']],['2026-W41','2026-W42'])
        self.assertEqual([x['count'] for x in r['buckets']],[1,2])
        self.assertEqual(period_bounds('week','2026-10-15')[0].isoformat(),'2026-10-12')
    def test_cancellation_recalculates_and_range(self):
        with connect(self.db) as d:d.execute("UPDATE orders SET status='cancelled' WHERE id='a'")
        r=get_history(connect,self.db,'2026-10-11','2026-10-12','day')
        self.assertEqual(r['summary']['order_count'],1)
        self.assertEqual(r['summary']['cancelled'],2)
        self.assertEqual(r['summary']['amount_cents'],8000)
        with self.assertRaises(ValueError):get_history(connect,self.db,'2020-01-01','2026-01-01')
        with self.assertRaises(ValueError):period_bounds('month','2026-10-15')
if __name__=='__main__':unittest.main()
