from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
def test_cashier_has_live_feed():
    html=(ROOT/'edge/static/cashier.html').read_text()
    js=(ROOT/'edge/static/cashier.js').read_text()
    assert 'id="liveOrders"' in html
    assert '/api/staff/orders' in js
    assert 'setInterval(loadLiveOrders,3000)' in js
    assert 'orderCard(o)' in js

def test_kiosk_does_not_touch_network():
    script=(ROOT/'ops/cashier_kiosk.sh').read_text()
    assert '127.0.0.1:18080/cashier' in script
    assert 'ifconfig' not in script
    assert 'ip link set' not in script
