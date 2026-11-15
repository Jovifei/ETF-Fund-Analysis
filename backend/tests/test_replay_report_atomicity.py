"""Atomicity contract for structure_weight_replay.write_report.

Covers the T4 fault-injection finding: when the Windows fallback path races a
concurrent writer, the failure-marker write must not mask the original error.
"""
import os

import pytest

from app.research import structure_weight_replay as replay

MIN_REPORT = {"manifest": {"m": 1}, "opportunities": [], "experiments": {}}


def test_preexisting_target_is_never_overwritten(tmp_path):
    target = tmp_path / "run"
    target.mkdir()
    (target / "OLD.json").write_text("old-report", encoding="utf-8")

    with pytest.raises(FileExistsError):
        replay.write_report(MIN_REPORT, target)

    assert (target / "OLD.json").read_text(encoding="utf-8") == "old-report"
    assert not (target / "INCOMPLETE").exists()  # reservation failed: no marker in user data


def test_windows_fallback_publishes_when_replace_is_denied(tmp_path, monkeypatch):
    target = tmp_path / "run"

    def deny(*_a, **_k):
        raise PermissionError("simulated windows rename onto existing directory")

    monkeypatch.setattr(os, "replace", deny)
    replay.write_report(MIN_REPORT, target)

    assert (target / "report.json").exists()
    assert not (target / "INCOMPLETE").exists()


def test_marker_failure_does_not_mask_original_error(tmp_path, monkeypatch):
    """A racer that takes the reservation must produce the real error, not the marker's."""
    target = tmp_path / "run"
    real_rmdir = os.rmdir

    def deny(*_a, **_k):
        raise PermissionError("simulated windows rename")

    def rmdir_then_race(path):
        real_rmdir(path)
        path_obj = type(target)(path)
        path_obj.write_text("racer", encoding="utf-8")

    monkeypatch.setattr(os, "replace", deny)
    monkeypatch.setattr(os, "rmdir", rmdir_then_race)

    with pytest.raises(Exception) as excinfo:
        replay.write_report(MIN_REPORT, target)

    message = str(excinfo.value)
    assert "INCOMPLETE" not in message, f"marker failure masked the original error: {message}"
    assert target.is_file(), "racer's file must survive"
    assert target.read_text(encoding="utf-8") == "racer"
