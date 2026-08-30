from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app


def test_screenshot_signal_board_static_contract():
    root = Path(__file__).parents[1] / "app" / "static"
    fragment = (root / "screenshot_signal_board.html").read_text(encoding="utf-8")
    script = (root / "screenshot_signal_board.js").read_text(encoding="utf-8")
    style = (root / "screenshot_signal_board.css").read_text(encoding="utf-8")
    for marker in (
        'id="screenshotSignalBoard"',
        "中国行业板块",
        "市场锚与跨市场代理",
        "盘中核心变化",
        "明日预测",
        "可加仓",
        "可入场",
        "可试探",
        "观望",
        "减仓",
    ):
        assert marker in fragment or marker in script
    for marker in (
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
    ):
        assert marker in script or marker in fragment
    assert "--cn-up:#ff5c62" in style
    assert "--cn-down:#1fe59a" in style
    assert "ETF代理池" in script
    assert "not_calibrated" in script


def test_industry_and_signal_board_api_shapes(bootstrapped):
    with TestClient(app) as client:
        industry = client.get("/api/industry-board")
        signal = client.get("/api/signal-board")
    assert industry.status_code == 200
    assert signal.status_code == 200
    industry_body = industry.json()
    signal_body = signal.json()
    assert industry_body["coverage"]["total"] == 31
    assert len(industry_body["market_anchors"]) == 4
    assert signal_body["version"].startswith("screenshot-signal-board")
    assert signal_body["breadth_scope"].startswith("ETF代理池")
    assert isinstance(signal_body["rows"], list)
    assert set(signal_body["group_counts"]).issubset({"add", "entry", "probe", "watch", "reduce"})
