from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app


STATIC = Path(__file__).resolve().parents[1] / 'app' / 'static'


def test_task_routes_land_on_the_intended_legacy_views() -> None:
    client = TestClient(app)
    expected = {
        '/holdings': '/legacy#holdings',
        '/research': '/legacy#signals',
        '/research/news': '/legacy#news',
        '/system': '/legacy#system',
    }
    for path, location in expected.items():
        response = client.get(path, follow_redirects=False)
        assert response.status_code == 307
        assert response.headers['location'] == location


def test_primary_pages_expose_task_navigation_not_historical_surfaces() -> None:
    pages = [
        STATIC / 'decision_board_workbuddy.html',
        STATIC / 'boards.html',
        STATIC / 'etf_detail.html',
        STATIC / 'etf_1430_workbench.html',
    ]
    for path in pages:
        html = path.read_text(encoding='utf-8')
        assert '🎯 决策' in html
        assert '🔥 板块' in html
        assert '💼 持仓' in html
        assert '🔬 研究' in html
        assert '📈 K线' not in html


def test_1430_is_secondary_mode_and_uses_canonical_grade_words() -> None:
    html = (STATIC / 'etf_1430_workbench.html').read_text(encoding='utf-8')
    js = (STATIC / 'etf_1430_workbench.js').read_text(encoding='utf-8')
    assert '14:30 尾盘模式' in html
    for grade in ('可加仓', '可入场', '可试探', '观望', '减仓'):
        assert grade in js
    for retired in ('买入候选', '持有/观察', '减仓候选', "action === '回避'"):
        assert retired not in js
    assert '历史上涨占比' in js


def test_decision_and_1430_rows_open_the_global_etf_detail() -> None:
    decision = (STATIC / 'decision_board_workbuddy.js').read_text(encoding='utf-8')
    tail = (STATIC / 'etf_1430_workbench.js').read_text(encoding='utf-8')
    assert 'window.location.assign(`/etf/${encodeURIComponent(tr.dataset.code)}`)' in decision
    assert 'window.location.assign(`/etf/${encodeURIComponent(row.dataset.code)}`)' in tail


def test_legacy_shell_uses_hash_router_for_research_holdings_and_system() -> None:
    html = (STATIC / 'index.html').read_text(encoding='utf-8')
    router = (STATIC / 'legacy_route.js').read_text(encoding='utf-8')
    assert 'legacy_route.js' in html
    assert '决策看板（兼容）' in html
    for key in ('signals', 'news', 'holdings', 'system'):
        assert f"{key}:" in router
