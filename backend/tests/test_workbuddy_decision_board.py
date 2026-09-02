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
    "操作建议",
)


def test_reference_board_is_primary_and_legacy_is_preserved() -> None:
    client = TestClient(app)

    primary = client.get("/")
    legacy = client.get("/legacy")
    compatibility = client.get("/workbench/1430", follow_redirects=False)

    assert primary.status_code == 200
    assert "K线企稳分析看板" in primary.text
    assert "盘中实时 v5" in primary.text
    assert "gradeCounters" in primary.text
    assert "tickerStrip" in primary.text
    assert "referenceLegend" in primary.text
    assert "marketSummary" in primary.text
    assert "boardArea" in primary.text
    assert "horizonSelect" in primary.text
    assert "/assets/decision_board_workbuddy.js" in primary.text
    assert "workbuddy.link" not in primary.text

    assert legacy.status_code == 200
    assert "ETF / LOF 决策台" in legacy.text

    assert compatibility.status_code == 307
    assert compatibility.headers["location"] == "/"


def test_reference_board_assets_and_columns_are_same_origin() -> None:
    client = TestClient(app)
    css = client.get("/assets/decision_board_workbuddy.css")
    js = client.get("/assets/decision_board_workbuddy.js")

    assert css.status_code == 200
    assert "decision-data-row" in css.text
    assert "grade-pill" in css.text
    assert "score-mini" in css.text
    assert "Microsoft YaHei" in css.text

    assert js.status_code == 200
    for label in REFERENCE_COLUMNS:
        assert label in js.text
    assert "明日预测" in js.text
    assert "J 90~100" in js.text
    assert "J>100" in js.text
    assert "量比" in js.text
    assert "conf " in js.text
    assert "WorkBuddyDecisionBoard" in js.text


def test_reference_legend_matches_company_thresholds() -> None:
    root = Path(__file__).parents[1] / "app" / "static"
    html = (root / "decision_board_workbuddy.html").read_text(encoding="utf-8")
    assert "放量≥1.15" in html
    assert "平量0.9~1.15" in html
    assert "缩量&lt;0.9" in html
    assert "RSI≥70" in html
    assert "J&gt;100" in html
    assert "J 90~100" in html
    assert "J 20~90" in html
    assert "conf≥60" in html


def test_reference_board_keeps_multi_user_session_auth():
    root = Path(__file__).parents[1] / "app" / "static"
    html = (root / "decision_board_workbuddy.html").read_text(encoding="utf-8")
    js = (root / "decision_board_workbuddy.js").read_text(encoding="utf-8")
    assert "identifierInput" in html and "passwordInput" in html and "logoutButton" in html
    assert "PRIVATE_ACCESS_TOKEN" not in html and "tokenInput" not in html
    assert "/api/auth/login" in js and "/api/auth/me" in js and "/api/auth/logout" in js
    assert "credentials:'same-origin'" in js and "X-CSRF-Token" in js
    assert "fundDecisionToken" not in js and "localStorage" not in js
