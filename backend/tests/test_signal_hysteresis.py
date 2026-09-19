from datetime import datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from app.services.signal_service import SignalService


def test_recovered_candidate_does_not_inherit_previous_data_anomaly():
    service = SignalService()
    now = datetime(2026, 9, 20, 10, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
    item = SimpleNamespace(state="观察", score=50.0, reasons=[])
    previous = SimpleNamespace(state="数据异常", score=50.0, as_of_time=now - timedelta(minutes=5))

    service._apply_state_hysteresis(item, previous, now)

    assert item.state == "观察"
