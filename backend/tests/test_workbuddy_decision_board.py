from pathlib import Path
from fastapi.testclient import TestClient

from app.main import app


def test_workbuddy_scoring_board_is_primary_and_legacy_is_preserved() -> None:
    client = TestClient(app)

    primary = client.get("/")
    legacy = client.get("/legacy")
    compatibility = client.get("/workbench/1430", follow_redirects=False)

    assert primary.status_code == 200
    assert "ETF 决策看板" in primary.text
    assert "五档分级 × 综合评分" in primary.text
    assert "scoreSummary" in primary.text
    assert "marketSummary" in primary.text
    assert "boardArea" in primary.text
    assert "horizonSelect" in primary.text
    assert "/assets/decision_board_workbuddy.js" in primary.text
    assert "workbuddy.link" not in primary.text

    assert legacy.status_code == 200
    assert "ETF / LOF 决策台" in legacy.text

    assert compatibility.status_code == 307
    assert compatibility.headers["location"] == "/"


def test_workbuddy_assets_are_served_from_same_origin() -> None:
    client = TestClient(app)
    css = client.get("/assets/decision_board_workbuddy.css")
    js = client.get("/assets/decision_board_workbuddy.js")

    assert css.status_code == 200
    assert "decision-data-row" in css.text
    assert "grade-pill" in css.text
    assert "score-badge" in css.text
    assert js.status_code == 200
    assert "J≥90" in js.text
    assert "KDJ死叉" in js.text
    assert "rowHtml" in js.text
    assert "WorkBuddyDecisionBoard" in js.text


def test_workbuddy_board_uses_multi_user_session_auth():
    root = Path(__file__).parents[1] / "app" / "static"
    html = (root / "decision_board_workbuddy.html").read_text(encoding="utf-8")
    js = (root / "decision_board_workbuddy.js").read_text(encoding="utf-8")
    assert "identifierInput" in html and "passwordInput" in html and "logoutButton" in html
    assert "PRIVATE_ACCESS_TOKEN" not in html and "tokenInput" not in html
    assert "/api/auth/login" in js and "/api/auth/me" in js and "/api/auth/logout" in js
    assert "credentials:'same-origin'" in js and "X-CSRF-Token" in js
    assert "fundDecisionToken" not in js and "localStorage" not in js
