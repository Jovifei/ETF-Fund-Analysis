from datetime import datetime
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event, select, text

from app.core.config import get_settings
from app.models import DailyBar
from app.services.history_audit import audit_history
from test_v103_history import instrument


def test_report_rejects_relative_names_and_excess_inventory(db_session):
    for codes in ([], ["588200"], ["../../private"], ["510300.SH"] * 51):
        with pytest.raises(ValueError):
            audit_history(db_session, get_settings(), codes)


def test_inspection_is_read_only_and_does_not_promote_raw_sina(db_session):
    item = instrument(db_session)
    bars = list(db_session.scalars(select(DailyBar).where(DailyBar.instrument_id == item.id).order_by(DailyBar.trade_date)))
    for row in bars:
        row.source = "akshare:sina:v102"
    bars[-2].close = 3.539
    bars[-1].close = 1.349
    bars[-1].open = 1.349
    bars[-1].amount = None
    db_session.flush()
    statements = []
    def capture(_conn, _cursor, statement, _params, _context, _many):
        statements.append(statement.lstrip().split()[0].upper())
    event.listen(db_session.get_bind(), "before_cursor_execute", capture)
    try:
        settings = get_settings().model_copy(update={"market_provider": "tushare", "tushare_token": ""})
        report = audit_history(db_session, settings, [item.ts_code, "000000.SH"],
            now=datetime(2026, 9, 11, 16, 0, tzinfo=settings.timezone))
    finally:
        event.remove(db_session.get_bind(), "before_cursor_execute", capture)
    row = report["items"][0]
    assert report["writes_performed"] is False and report["provider_called"] is False
    assert row["actionable"] is False and row["candidate_recompute_allowed"] is False
    assert "sina_absolute_units_unverified" in row["blockers"]
    assert row["unexplained_break_count"] >= 1
    assert row["missing_or_invalid_amount"] == 1
    assert report["items"][1]["blockers"] == ["instrument_not_in_catalog"]
    assert statements and set(statements) == {"SELECT"}
    assert bars[-2].close == 3.539 and bars[-1].close == 1.349
    assert row["corporate_action_verification"] == "not_asserted"


def test_readonly_sqlite_connection_rejects_accidental_writes(tmp_path, monkeypatch):
    script = Path(__file__).resolve().parents[2] / "scripts/audit_research_inputs.py"
    spec = spec_from_file_location("audit_readonly_cli", script)
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    path = tmp_path / "audit.sqlite"
    engine = create_engine("sqlite:///" + str(path))
    with engine.begin() as c:
        c.execute(text("CREATE TABLE sentinel (id INTEGER)"))
        c.execute(text("INSERT INTO sentinel VALUES (1)"))
    engine.dispose()
    def unexpected_writer(db, _settings, _codes):
        db.execute(text("DELETE FROM sentinel"))
    monkeypatch.setattr(module, "audit_history", unexpected_writer)
    settings = get_settings().model_copy(update={"database_url": "sqlite:///" + str(path)})
    from sqlalchemy.exc import OperationalError
    with pytest.raises(OperationalError):
        module.read_only_audit(settings, ["510300.SH"])
    engine = create_engine(settings.database_url)
    with engine.connect() as c:
        assert c.scalar(text("SELECT COUNT(*) FROM sentinel")) == 1
    engine.dispose()


def test_readonly_cli_never_creates_a_missing_database(tmp_path):
    script = Path(__file__).resolve().parents[2] / "scripts/audit_research_inputs.py"
    spec = spec_from_file_location("audit_readonly_missing", script)
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    path = tmp_path / "does-not-exist.sqlite"
    settings = get_settings().model_copy(update={"database_url": "sqlite:///" + str(path)})
    with pytest.raises(ValueError, match="existing_regular"):
        module.read_only_audit(settings, ["510300.SH"])
    assert not path.exists()
