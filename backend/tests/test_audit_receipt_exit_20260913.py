"""CLI receipt success must not conceal indicator-only blockers."""
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import json
import sys

import pytest


def cli():
    path = Path(__file__).resolve().parents[2] / "scripts/audit_research_inputs.py"
    spec = spec_from_file_location("audit_receipt_cli", path)
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def report():
    return {"items": [
        {"blockers": [], "indicator_blockers": ["indicator_version_mismatch"]},
        {"blockers": ["sina_absolute_units_unverified"], "indicator_blockers": ["indicator_missing"]},
        {"blockers": [], "indicator_blockers": []},
    ], "writes_performed": False, "provider_called": False, "actionable": False}


def test_receipt_counts_indicator_only_blockers_without_double_counting():
    summary = cli().summarize_audit(report())
    assert summary["instruments"] == 3
    assert summary["history_blocked"] == 1
    assert summary["indicator_blocked"] == 2
    assert summary["blocked"] == 2
    assert summary["qualification_granted"] is False


@pytest.mark.parametrize("strict,code", [(False, 0), (True, 3)])
def test_cli_always_writes_receipt_but_strict_mode_fails_for_blockers(tmp_path, monkeypatch, capsys, strict, code):
    module = cli()
    output = tmp_path / "new-receipt.json"
    monkeypatch.setattr(module, "read_only_audit", lambda *_: report())
    args = ["audit_research_inputs.py", "--codes", "510300.SH", "--output", str(output)]
    monkeypatch.setattr(sys, "argv", args + (["--fail-on-blockers"] if strict else []))
    assert module.main() == code
    assert json.loads(output.read_text(encoding="utf-8")) == report()
    summary = json.loads(capsys.readouterr().out)
    assert summary["audit_written"] is True and summary["blocked"] == 2
    assert summary["qualification_granted"] is False


def test_strict_clean_receipt_still_never_grants_qualification(tmp_path, monkeypatch, capsys):
    module = cli()
    monkeypatch.setattr(module, "read_only_audit", lambda *_: {"items": [report()["items"][2]]})
    monkeypatch.setattr(sys, "argv", ["audit", "--codes", "510300.SH", "--output", str(tmp_path / "clean.json"), "--fail-on-blockers"])
    assert module.main() == 0
    assert json.loads(capsys.readouterr().out)["qualification_granted"] is False
