"""Cloud-only historical operations analytics. All monetary values are order amounts, not payments."""
from datetime import date, datetime, timedelta, timezone

BEIJING = timezone(timedelta(hours=8))
MAX_RANGE = 366

def today_beijing():
    return datetime.now(BEIJING).date()

def parse_day(s):
    if not isinstance(s, str) or len(s) != 10:
        raise ValueError('日期格式应为 YYYY-MM-DD')
    d = date.fromisoformat(s)
    if d.isoformat() != s:
        raise ValueError('无效日期')
    return d

def period_bounds(period, anchor):
    d = parse_day(anchor)
    if period == 'day':
        return d, d
    if period == 'week':
        start = d - timedelta(days=d.weekday())
        return start, start + timedelta(days=6)
    raise ValueError('仅支持 day/week')

def get_history(connect, path, start, end, group='day'):
    start, end = parse_day(start), parse_day(end)
    if end < start or (end - start).days >= MAX_RANGE:
        raise ValueError('日期范围必须为 1–366 天')
    if group not in ('day', 'week'):
        raise ValueError('分组必须是 day 或 week')
    with connect(path) as db:
        orders = [dict(r) for r in db.execute('''
            SELECT id, created_at, status, source, total_cents
            FROM orders WHERE created_at >= ? AND created_at < ?
            ORDER BY created_at''', (start.isoformat(), (end+timedelta(days=1)).isoformat()))]
        # Order-item price/name snapshots preserve history across price changes.
        items = [dict(r) for r in db.execute('''
            SELECT i.order_id, i.menu_id, i.name, i.qty, i.price_cents
            FROM order_items i JOIN orders o ON i.order_id=o.id
            WHERE o.created_at >= ? AND o.created_at < ? AND o.status!='cancelled'
            ORDER BY i.order_id,i.menu_id''', (start.isoformat(), (end+timedelta(days=1)).isoformat()))]
    items_by_order = {}
    for i in items:
        items_by_order.setdefault(i['order_id'], []).append(i)
    by_day = {}
    hours = [0] * 24
    weekdays = [{'weekday':i,'count':0,'amount_cents':0} for i in range(7)]
    dishes = {}
    sources = {'customer':0, 'cashier':0}
    cancelled = 0
    completed = 0
    valid_orders = 0
    total_cents = 0
    for o in orders:
        try:
            d = date.fromisoformat(o['created_at'][:10])
            h = int(o['created_at'][11:13])
        except (ValueError, TypeError):
            continue
        if o['status'] == 'cancelled':
            cancelled += 1
            continue
        count = by_day.setdefault(d.isoformat(), {'day':d.isoformat(),'count':0,'amount_cents':0,'items_sold':0})
        count['count'] += 1
        count['amount_cents'] += o['total_cents']
        valid_orders += 1
        total_cents += o['total_cents']
        completed += (o['status'] == 'completed')
        if 0 <= h < 24: hours[h] += 1
        weekdays[d.weekday()]['count'] += 1
        weekdays[d.weekday()]['amount_cents'] += o['total_cents']
        if o['source'] in sources: sources[o['source']] += 1
        for i in items_by_order.get(o['id'], []):
            key = (i['menu_id'], i['name'])
            dish = dishes.setdefault(key, {'menu_id':i['menu_id'],'name':i['name'], 'qty':0,'amount_cents':0})
            dish['qty'] += i['qty']
            dish['amount_cents'] += i['qty'] * i['price_cents']
            count['items_sold'] += i['qty']
    buckets = {}
    d = start
    while d <= end:
        key = d.isoformat() if group == 'day' else f'{d.isocalendar().year}-W{d.isocalendar().week:02d}'
        b = buckets.setdefault(key, {'period':key,'count':0,'amount_cents':0,'items_sold':0})
        record = by_day.get(d.isoformat())
        if record:
            for field in ('count','amount_cents','items_sold'): b[field] += record[field]
        d += timedelta(days=1)
    top_dishes = sorted(dishes.values(), key=lambda x:(-x['qty'],-x['amount_cents'],x['name']))[:30]
    return {
        'start':start.isoformat(), 'end':end.isoformat(), 'group':group,
        'timezone':'Asia/Shanghai', 'today':today_beijing().isoformat(),
        'summary': {'order_count': valid_orders,'amount_cents':total_cents,
                    'avg_order_cents':round(total_cents/valid_orders) if valid_orders else 0,
                    'completed':completed,'cancelled':cancelled,
                    'items_sold':sum(x['qty'] for x in dishes.values()),
                    'customer_orders':sources['customer'],'cashier_orders':sources['cashier']},
        'buckets':list(buckets.values()),
        'by_hour':[{'hour':i,'count':v} for i,v in enumerate(hours)],
        'by_weekday':weekdays, 'top_dishes':top_dishes
    }
