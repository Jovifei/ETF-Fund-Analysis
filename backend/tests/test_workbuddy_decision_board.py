from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app


REFERENCE_COLUMNS = (
    "标的",
    "今日涨幅",
    "较昨日",
    "量能",
    "均线多空",
    "MACD",
    "KDJ",
    "九转",
    "RSI",
    "板块涨跌",
    "近1周",
    "明日预测",
    "操作建议",
)


def test_reference_v4_decision_board_is_primary_and_legacy_is_preserved() -> None:
    client = TestClient(app)
    primary = client.get("/")
    legacy = client.get("/legacy")
    compatibility = client.get("/workbench/1430", follow_redirects=False)

    assert primary.status_code == 200
    assert "K线企稳分析看板" in primary.text
    assert "gradeSummary" in primary.text
    assert "moverStrip" in primary.text
    assert "legendBody" in primary.text
    assert "marketSummary" in primary.text
    assert "insightGrid" in primary.text
    assert "boardArea" in primary.text
    assert "horizonSelect" in primary.text
    assert "/assets/decision_board_workbuddy.js" in primary.text
    assert "workbuddy.link" not in primary.text

    assert legacy.status_code == 200
    assert "ETF / LOF 决策台" in legacy.text
    assert compatibility.status_code == 307
    assert compatibility.headers["location"] == "/"


def test_reference_v4_assets_keep_exact_main_table_contract() -> None:
    root = Path(__file__).parents[1] / "app" / "static"
    html = (root / "decision_board_workbuddy.html").read_text(encoding="utf-8")
    js = (root / "decision_board_workbuddy.js").read_text(encoding="utf-8")
    css = (root / "decision_board_workbuddy.css").read_text(encoding="utf-8")

    for column in REFERENCE_COLUMNS:
        assert column in js
    assert "综合分" not in REFERENCE_COLUMNS
    assert "score-mini" in js and "score-mini" in css
    assert "J 90~100" in js and "J>100" in js
    assert "放量≥1.15" in js or "放量≥1.15" in html
    assert "平量0.90~1.15" in js or "平量0.90~1.15" in html
    assert "强势金叉" in js and "修复延续" in js and "将死叉" in js
    assert "盘中核心变化（对比昨日）" in js
    assert "形态匹配 + 置信度解读" in js
    assert "数据来源：" in html
    assert "Microsoft YaHei" in css


def test_reference_v4_board_uses_multi_user_session_auth() -> None:
    root = Path(__file__).parents[1] / "app" / "static"
    html = (root / "decision_board_workbuddy.html").read_text(encoding="utf-8")
    js = (root / "decision_board_workbuddy.js").read_text(encoding="utf-8")
    assert "identifierInput" in html and "passwordInput" in html and "logoutButton" in html
    assert "PRIVATE_ACCESS_TOKEN" not in html and "tokenInput" not in html
    assert "/api/auth/login" in js and "/api/auth/me" in js and "/api/auth/logout" in js
    assert "credentials:'same-origin'" in js and "X-CSRF-Token" in js
    assert "fundDecisionToken" not in js and "localStorage" not in js


def test_reference_v4_css_uses_reference_market_color_semantics() -> None:
    css = (Path(__file__).parents[1] / "app" / "static" / "decision_board_workbuddy.css").read_text(encoding="utf-8")
    assert ".price-up" in css and "var(--red)" in css
    assert ".price-down" in css and "var(--green)" in css
    assert ".delta-arrow.up" in css and "color:#36dc8d" in css
    assert ".delta-arrow.down" in css and "color:#ff5852" in css
    assert ".sector-up" in css and ".sector-down" in css
