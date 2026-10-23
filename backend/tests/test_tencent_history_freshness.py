"""Offline transport regressions; these do not qualify real market data."""
from __future__ import annotations

import importlib
import json
from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from app.providers import bounded_sdk


class CapturedPipe:
    def send_bytes(self, payload):
        self.payload = json.loads(payload)

    def close(self):
        self.closed = True


def child_call(name="stock_zh_a_hist_tx", **params):
    if name == "stock_zh_a_hist_tx":
        params.setdefault("end_date", "20261023")
    pipe = CapturedPipe()
    bounded_sdk._child(pipe, "akshare", name, params, None, 7)
    assert pipe.closed is True
    return pipe.payload


def set_market_clock(monkeypatch, at):
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            assert str(tz) == "Asia/Shanghai"
            return at.astimezone(tz)
    monkeypatch.setattr(bounded_sdk, "datetime", Clock, raising=False)


@pytest.fixture(autouse=True)
def after_close_clock(monkeypatch):
    set_market_clock(monkeypatch, datetime(2026, 10, 23, 7, 15, tzinfo=ZoneInfo("UTC")))


def test_installed_tencent_sdk_does_not_reuse_morning_response_key(monkeypatch):
    """Exercise the installed parser while every HTTP request remains offline."""
    pytest.importorskip("akshare")
    sdk = importlib.import_module("akshare.stock_feature.stock_hist_tx")
    requests, cached = [], {}
    upstream = {"has_target": False}

    def offline_get(url, *, params, timeout):
        requests.append((url, dict(params), timeout))
        key = (url, tuple(sorted(params.items())))
        if key not in cached:
            days = ["2026-10-22"] + (["2026-10-23"] if upstream["has_target"] else [])
            rows = [[day, "1.2", "1.2", "1.3", "1.1", "10", "0", "1", "0.12"] for day in days]
            cached[key] = SimpleNamespace(text="kline_day2026=" + json.dumps({
                "data": {"sh510300": {"day": rows}},
            }))
        return cached[key]

    original_requests = SimpleNamespace(get=offline_get)
    monkeypatch.setattr(sdk, "requests", original_requests)
    monkeypatch.setattr(sdk, "get_tx_start_year", lambda **_: "2026-01-01")
    monkeypatch.setattr(sdk, "get_tqdm", lambda: lambda iterable, **_: iterable)
    params = dict(symbol="sh510300", start_date="20261016", end_date="20261023", adjust="", timeout=7)

    set_market_clock(monkeypatch, datetime(2026, 10, 23, 1, 30, tzinfo=ZoneInfo("UTC")))
    morning = child_call(**{**params, "end_date": "20261022"})
    upstream["has_target"] = True
    set_market_clock(monkeypatch, datetime(2026, 10, 23, 7, 15, tzinfo=ZoneInfo("UTC")))
    close = child_call(**params)

    assert morning["ok"] is close["ok"] is True
    assert morning["records"][-1]["date"][:10] == "2026-10-22"
    assert close["records"][-1]["date"][:10] == "2026-10-23"
    assert requests[0][1]["r"] != requests[1][1]["r"]
    assert requests[0][1]["param"] == requests[1][1]["param"]
    assert requests[0][2] == requests[1][2] == 7
    assert close["records"][-1]["volume"] == 1000
    assert close["records"][-1]["amount"] == 1200
    assert sdk.requests is original_requests


def _injected_sdk(monkeypatch, *, failure=None):
    calls = []
    shared_params = {"param": "sh510300,day,2026-01-01,2027-12-31,640,", "r": "fixed"}

    def get(url, **kwargs):
        calls.append((url, kwargs))
        if failure:
            raise failure
        return SimpleNamespace()

    client = SimpleNamespace(get=get)
    namespace = {"requests": client, "shared_params": shared_params}
    exec("def history(**params):\n"
         "    requests.get('https://proxy.finance.qq.com/ifzqgtimg/appstock/app/newfqkline/get', params=shared_params, timeout=7)\n"
         "    requests.get('https://example.invalid/other', params=shared_params, timeout=7)\n"
         "    return []\n", namespace)
    function = namespace["history"]
    module = SimpleNamespace(stock_zh_a_hist_tx=function, fund_etf_hist_em=function)
    monkeypatch.setattr(bounded_sdk.importlib, "import_module", lambda _: module)
    return calls, namespace, client, shared_params


def test_freshness_changes_only_tencent_history_request_without_mutating_sdk_state(monkeypatch):
    calls, namespace, client, shared_params = _injected_sdk(monkeypatch)

    assert child_call()["ok"] is True

    assert calls[0][1]["params"]["r"] != "fixed"
    assert calls[0][1]["params"]["param"] == shared_params["param"]
    assert calls[1][1]["params"] == shared_params
    assert shared_params["r"] == "fixed"
    assert namespace["requests"] is client


def test_unrelated_sdk_operation_keeps_its_request_parameters(monkeypatch):
    calls, namespace, client, shared_params = _injected_sdk(monkeypatch)

    assert child_call("fund_etf_hist_em")["ok"] is True

    assert all(kwargs["params"] == shared_params for _, kwargs in calls)
    assert namespace["requests"] is client


@pytest.mark.parametrize("at,end_date", [
    (datetime(2026, 10, 23, 7, 14, 59, tzinfo=ZoneInfo("UTC")), "20261023"),
    (datetime(2026, 10, 23, 7, 15, tzinfo=ZoneInfo("UTC")), "20261022"),
    (datetime(2026, 10, 23, 7, 15, tzinfo=ZoneInfo("UTC")), "20261024"),
    (datetime(2026, 10, 23, 7, 15, tzinfo=ZoneInfo("UTC")), "invalid"),
    (datetime(2026, 10, 22, 16, 30, tzinfo=ZoneInfo("UTC")), "20261023"),
])
def test_before_shanghai_cutoff_or_other_target_keeps_cache_key(monkeypatch, at, end_date):
    calls, _, _, shared_params = _injected_sdk(monkeypatch)
    set_market_clock(monkeypatch, at)

    assert child_call(end_date=end_date)["ok"] is True

    assert all(kwargs["params"] == shared_params for _, kwargs in calls)


def test_tencent_sdk_failure_keeps_sanitized_payload_and_original_transport(monkeypatch):
    _, namespace, client, shared_params = _injected_sdk(
        monkeypatch, failure=TimeoutError("fixture private URL and credential must not escape"),
    )

    result = child_call()

    assert result == {"ok": False, "code": "provider_failed", "unsupported": False}
    assert namespace["requests"] is client
    assert shared_params["r"] == "fixed"


def test_fresh_tencent_child_preserves_bounded_response_limit(monkeypatch):
    _injected_sdk(monkeypatch)
    monkeypatch.setattr(bounded_sdk, "MAX_BYTES", 1)

    assert child_call() == {"ok": False, "code": "response_too_large", "unsupported": False}


def test_unrecognized_sdk_transport_fails_closed_without_parent_patch(monkeypatch):
    module = SimpleNamespace(stock_zh_a_hist_tx=lambda **_: [])
    monkeypatch.setattr(bounded_sdk.importlib, "import_module", lambda _: module)

    assert child_call() == {"ok": False, "code": "endpoint_unavailable", "unsupported": True}
