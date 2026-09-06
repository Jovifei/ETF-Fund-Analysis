from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app


STATIC = Path(__file__).resolve().parents[1] / "app" / "static"


def test_task_routes_are_first_class_urls() -> None:
    client = TestClient(app)
    expected_tokens = {
        "/holdings": "legacy_route.js",
        "/research": "legacy_route.js",
        "/research/news": "legacy_route.js",
        "/system": "legacy_route.js",
        "/decision/1430": "ETF 决策 · 14:30 尾盘模式",
    }
    for path, token in expected_tokens.items():
        response = client.get(path, follow_redirects=False)
        assert response.status_code == 200, f"{path} unexpectedly redirected"
        assert token in response.text


def test_legacy_bookmarks_redirect_to_task_urls() -> None:
    client = TestClient(app)
    expected = {
        "/legacy": "/research",
        "/assets/index.html": "/research",
        "/workbench/1430": "/decision/1430",
        "/assets/etf_1430_workbench.html": "/decision/1430",
        "/workbench/kline": "/",
        "/assets/kline_stabilization.html": "/",
    }
    for path, location in expected.items():
        response = client.get(path, follow_redirects=False)
        assert response.status_code == 307
        assert response.headers["location"] == location


def test_primary_pages_expose_task_navigation_not_historical_surfaces() -> None:
    pages = [
        STATIC / "decision_board_workbuddy.html",
        STATIC / "boards.html",
        STATIC / "etf_detail.html",
        STATIC / "etf_1430_workbench.html",
        STATIC / "index.html",
    ]
    shell_js = (STATIC / "app_shell.js").read_text(encoding="utf-8")
    # v0.8.2 统一壳：一级导航唯一来源是 app_shell.js（SVG 图标 + 文字标签），
    # 每个一级页面只承载壳挂载点；跨页位置/字体由 shell.css 固定。
    for label in ("决策", "板块", "持仓", "研究", "个人中心"):
        assert f'label: \'{label}\'' in shell_js, f"shell nav missing {label}"
    for href in ("/boards", "/holdings", "/research", "/account"):
        assert f"href: '{href}'" in shell_js
    assert "K线" not in shell_js
    assert "/legacy" not in shell_js and "/workbench/kline" not in shell_js

    for path in pages:
        html = path.read_text(encoding="utf-8")
        assert 'id="shellTopbar"' in html, f"{path} missing shell mount"
        assert "app_shell.js" in html, f"{path} missing shell script"
        assert "shell.css" in html, f"{path} missing shell css"
        assert "📈 K线" not in html
        assert 'href="/legacy"' not in html
        assert 'href="/workbench/kline"' not in html

    decision = (STATIC / "decision_board_workbuddy.html").read_text(encoding="utf-8")
    decision_js = (STATIC / "decision_board_workbuddy.js").read_text(encoding="utf-8")
    assert "/decision/1430" in decision_js
    assert 'href="/workbench/1430"' not in decision


def test_1430_is_secondary_mode_and_uses_canonical_grade_words() -> None:
    html = (STATIC / "etf_1430_workbench.html").read_text(encoding="utf-8")
    js = (STATIC / "etf_1430_workbench.js").read_text(encoding="utf-8")
    assert "ETF 决策 · 14:30 尾盘模式" in html
    assert "14:30 尾盘模式" in html
    for grade in ("可加仓", "可入场", "可试探", "观望", "减仓"):
        assert grade in js
    for retired in ("买入候选", "持有/观察", "减仓候选", "action === '回避'"):
        assert retired not in js
    assert "历史上涨占比" in js


def test_decision_and_1430_rows_open_the_global_etf_detail() -> None:
    decision = (STATIC / "decision_board_workbuddy.js").read_text(encoding="utf-8")
    tail = (STATIC / "etf_1430_workbench.js").read_text(encoding="utf-8")
    assert "window.location.assign(`/etf/${encodeURIComponent(tr.dataset.code)}`)" in decision
    assert "window.location.assign(`/etf/${encodeURIComponent(row.dataset.code)}`)" in tail


def test_research_shell_routes_by_canonical_path_and_keeps_hash_compatibility() -> None:
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    router = (STATIC / "legacy_route.js").read_text(encoding="utf-8")
    assert "legacy_route.js" in html
    assert "决策看板（兼容）" in html
    for path in ("/holdings", "/system", "/research/news", "/research"):
        assert path in router
    for key in ("signals", "news", "holdings", "system"):
        assert f"{key}:" in router
