"""Pure stdlib/static contract tests, runnable even before installing Flask."""
import ast
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def test_python_compiles():
    for path in [*ROOT.glob('edge/*.py'),*ROOT.glob('cloud/*.py'),*ROOT.glob('ops/*.py')]:
        ast.parse(path.read_text(encoding='utf-8'))
def test_menu_image_assets_are_valid_webp():
    images=list((ROOT/'edge/static/images').glob('*.webp'))
    assert len(images)>=12
    for p in images:
        b=p.read_bytes()
        assert b[:4]==b'RIFF' and b[8:12]==b'WEBP'
        assert int.from_bytes(b[4:8],'little')+8==len(b)
def test_frontend_auto_refresh_and_price_snapshots():
    js=(ROOT/'edge/static/customer.js').read_text()
    app=(ROOT/'edge/app.py').read_text()
    manage=(ROOT/'edge/static/manage.js').read_text()
    assert 'setInterval(checkMenu,3000)' in js
    assert "'/api/menu-revision'" in js
    assert "price_cents:dish.price_cents" in js
    assert '409' in js
    assert "'price_cents'" in app and '历史' in (ROOT/'README.md').read_text()
    assert "new FormData()" in manage and "imageWebp" in manage
    assert "'/media/'" in (ROOT/'edge/db.py').read_text()
def test_separate_deploy_ports():
    assert '18080:8000' in (ROOT/'edge/compose.yaml').read_text()
    assert '15001:8000' in (ROOT/'cloud/compose.yaml').read_text()
