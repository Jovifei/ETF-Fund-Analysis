import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.mark.parametrize("interruption", [KeyboardInterrupt, SystemExit])
def test_phase_diagnostic_does_not_report_interruption_as_success(interruption):
    path = Path(__file__).resolve().parents[2] / "scripts" / "run_local_compute.py"
    spec = importlib.util.spec_from_file_location("diagnostic_interrupt_cli", path)
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    events = []
    args = SimpleNamespace(_on_diagnostic=lambda phase, **event: events.append(event))
    with pytest.raises(interruption):
        with cli.phase_diagnostic(args, "projection_export"):
            raise interruption("private detail must never enter diagnostics")
    assert len(events) == 1 and events[0]["status"] == "failed"
    assert events[0]["error_type"] == "Exception"
    assert "private" not in str(events)
