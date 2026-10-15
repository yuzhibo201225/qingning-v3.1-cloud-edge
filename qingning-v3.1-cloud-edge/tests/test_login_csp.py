"""Regression guard for the login bug observed on Raspberry Pi Firefox."""
from pathlib import Path
import re
ROOT=Path(__file__).resolve().parents[1]
def test_login_does_not_use_inline_script_blocked_by_csp():
    html=(ROOT/'edge/static/login.html').read_text(encoding='utf8')
    assert '<script src="/static/login.js"></script>' in html
    assert not re.search(r'<script\s*>(.*?)</script>',html,re.S)
    js=(ROOT/'edge/static/login.js').read_text(encoding='utf8')
    assert 'loginBtn' in js and '/api/login' in js
