import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from urllib.parse import quote
import publish


def test_index_template_supports_system_dark_mode():
    """落地页跟随系统深色模式：颜色走变量，暗色下重设变量值。"""
    html = publish.build_index_html({})
    assert "color-scheme: light dark;" in html
    assert "@media (prefers-color-scheme: dark)" in html
    assert "background: var(--bg-page);" in html
    assert "color-scheme: light;" not in html


def test_index_card_links_and_badges():
    manifest = {
        "BV1xx": {"folder": "示例书名", "title": "示例书名", "updated": "2026-01-02T03:04:05+08:00",
                  "corrected": True},
    }
    html = publish.build_index_html(manifest)
    assert f'href="{quote("示例书名")}/book.html"' in html
    assert "字幕对照" in html
    assert 'class="badge b0"' in html
