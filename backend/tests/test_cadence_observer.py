import importlib.util
import json
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from app.workspace.local_stability import RESEARCH_TABLES, REPORT_VERSION
from test_local_stability import jobs as complete_ledger, SCOPE


SCRIPT = Path(__file__).parents[2] / "scripts" / "observe_local_cadence.py"
spec = importlib.util.spec_from_file_location("cadence_observer_test", SCRIPT)
observer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(observer)

SHA, CONFIG, IMAGE = "a" * 40, "b" * 64, "sha256:" + "c" * 64
ZONE = ZoneInfo("Asia/Shanghai")


class Calendar:
    def decision(self, day):
        return SimpleNamespace(verified=True, is_trade_day=day.weekday() < 5, source="test-XSHG")


def cloud(when):
    return {"captured_at": when.isoformat(), "transaction_read_only": "on",
            "transaction_isolation": "repeatable read", "database_oid": "16384",
            "server_start": "2026-10-13T22:25:09.55433+08:00", "stats_reset": None,
            "schema_heads": ["f0"], "tables": [
                {"table_name": table, "exact_count": 100, "n_tup_ins": 100,
                 "n_tup_upd": 0, "n_tup_del": 0, "heap_bytes": 8192, "total_bytes": 16384}
                for table in RESEARCH_TABLES]}


def runtime(when):
    return {"captured_at": when.isoformat(), "source_sha": SHA, "services": [
        {"role": role, "image_id": IMAGE, "state": "running", "restart_count": 0,
         "oom_killed": False, "started_at": "2026-10-16T00:00:00Z",
         "health": "disabled" if role == "scheduler" else "healthy",
         "scheduler_enabled": False, "workspace_research_source": "local_bundle"}
        for role in ("api", "worker", "scheduler")]}


class Runner:
    def __init__(self, when):
        self.when, self.calls = when, []
        self.fail = None

    def __call__(self, command, **kwargs):
        self.calls.append((command, kwargs))
        assert kwargs["timeout"] <= 120
        if self.fail and command[0] == self.fail:
            return SimpleNamespace(returncode=1, stdout="", stderr="private URL must be suppressed")
        if command[0] == "scp":
            Path(command[-1]).write_text(json.dumps(cloud(self.when)), encoding="utf-8")
            out = ""
        elif command[0] == "powershell.exe":
            out = json.dumps({"task_name": "ETF-Local-Live-Compute", "state": "Ready",
                              "last_result": 0, "last_run_at": self.when.isoformat(),
                              "next_run_at": self.when.isoformat(), "action_sha": SHA})
        elif command[-1] == "-":
            out = json.dumps(runtime(self.when))
        else:
            phase = command[-1]
            out = json.dumps({"receipt": str(observer.REMOTE_DIRECTORY) + f"/research-counts-{phase}-1792000000.json",
                              "readonly": True, "tables": 14})
        return SimpleNamespace(returncode=0, stdout=out, stderr="")


@pytest.fixture
def owned(tmp_path, monkeypatch):
    root = tmp_path / "owned"
    root.mkdir()
    (root / ".local-live").touch()
    monkeypatch.setattr(observer, "DOWNLOAD_ROOT", tmp_path / "downloads")
    return root


def invoke(root, mode="before", when=None, runner=None, **overrides):
    when = when or datetime(2026, 10, 16, 13, 50, tzinfo=ZONE)
    args = dict(mode=mode, root=root, session=date(2026, 10, 16),
                expected_source_sha=SHA, expected_config_hash=CONFIG, expected_image_id=IMAGE,
                expected_scope_hash=SCOPE,
                calendar=Calendar(), now=lambda: when, runner=runner or Runner(when))
    args.update(overrides)
    return observer.observe(**args)


def ledger(day="2026-10-16"):
    return complete_ledger(day)


def test_before_capture_uses_fixed_alias_and_preserves_immutable_baseline(owned):
    when = datetime(2026, 10, 16, 13, 50, tzinfo=ZONE)
    runner = Runner(when)
    result = invoke(owned, runner=runner)
    assert result["state"] == "CAPTURED"
    assert result["natural_trigger"]["state"] == "NOT_RUN"
    assert any(call[0][0] == "scp" for call in runner.calls)
    assert all("aliyun-etf" in call[0] or call[0][0] == "powershell.exe" or call[0][0] == "scp"
               for call in runner.calls)
    count = len(runner.calls)
    assert invoke(owned, runner=runner)["state"] == "ALREADY_CAPTURED"
    assert len(runner.calls) == count


@pytest.mark.parametrize("when", [datetime(2026, 10, 16, 13, 49, tzinfo=ZONE),
                                  datetime(2026, 10, 16, 13, 55, tzinfo=ZONE),
                                  datetime(2026, 10, 17, 13, 50, tzinfo=ZONE)])
def test_before_missing_window_or_wrong_day_does_not_call_network(owned, when):
    runner = Runner(when)
    assert invoke(owned, when=when, runner=runner)["state"] == "PARTIAL"
    assert runner.calls == []


def test_after_missing_baseline_cannot_be_invented(owned):
    when = datetime(2026, 10, 16, 16, 35, tzinfo=ZONE)
    runner = Runner(when)
    assert invoke(owned, "after", when, runner)["state"] == "PARTIAL"
    assert runner.calls == []


def test_external_command_failure_is_sanitized_and_not_retried(owned):
    runner = Runner(datetime(2026, 10, 16, 13, 50, tzinfo=ZONE))
    runner.fail = "ssh"
    result = invoke(owned, runner=runner)
    assert result["state"] == "UNKNOWN"
    assert "private URL" not in json.dumps(result)
    assert len(runner.calls) == 1
    attempts = list((owned / "receipts" / "stability-observations" / "2026-10-16" / "attempts").glob("*.json"))
    assert len(attempts) == 1


def test_runtime_program_outputs_only_selected_metadata():
    program = observer.RUNTIME_PROGRAM
    assert "json .Config.Env" not in program
    assert "Health.Log" not in program
    assert "producer_auth" not in program
    assert "GIT_COMMIT_SHA" in program
    assert "SCHEDULER_ENABLED" in program
    assert "WORKSPACE_RESEARCH_SOURCE" in program
    assert all(name in program for name in ("etf-workspace-v108-production-api",
                                           "etf-workspace-v108-production-worker",
                                           "etf-workspace-v108-production-scheduler"))


def test_remote_program_parses_selected_fields_and_scheduler_none(monkeypatch, capsys):
    import subprocess
    templates = []
    def inspect(command, **kwargs):
        assert command[:3] == ["docker", "inspect", "--format"]
        templates.append(command[3])
        role = command[-1].split("-")[-1]
        state = {"state": "running", "started_at": "2026-10-16T00:00:00Z",
                 "restart_count": 0, "oom_killed": False, "image_id": IMAGE,
                 "health": "healthy" if role != "scheduler" else None,
                 "healthcheck_test": ["NONE"] if role == "scheduler" else ["CMD", "probe"]}
        lines = [json.dumps(state), json.dumps("GIT_COMMIT_SHA=" + SHA),
                 json.dumps("SCHEDULER_ENABLED=false"), json.dumps("WORKSPACE_RESEARCH_SOURCE=local_bundle")]
        return SimpleNamespace(returncode=0, stdout="\n".join(lines).encode(), stderr=b"")
    monkeypatch.setattr(subprocess, "run", inspect)
    exec(compile(observer.RUNTIME_PROGRAM, "runtime-observer", "exec"), {})
    value = json.loads(capsys.readouterr().out)
    assert value["source_sha"] == SHA
    assert value["services"][-1]["health"] == "disabled"
    assert value["services"][-1]["scheduler_enabled"] is False
    assert all('{{printf "\\n"}}' in template for template in templates)
    assert all('{{json .Config.Env}}' not in template for template in templates)


def test_after_assesses_real_paths_without_claiming_two_days(owned, monkeypatch):
    invoke(owned)
    monkeypatch.setattr(observer, "load_ledger", lambda root, session: ledger())
    result = invoke(owned, "after", datetime(2026, 10, 16, 16, 35, tzinfo=ZONE))
    assert result["state"] == "PASS"
    assert result["two_day_state"] == "PARTIAL"
    assert result["natural_trigger"]["state"] == "NOT_RUN"
    assert invoke(owned, "summary")["state"] == "PARTIAL"


def test_reparse_root_and_unowned_root_rejected_before_network(tmp_path):
    with pytest.raises(ValueError, match="owned"):
        invoke(tmp_path)


def test_different_runtime_or_task_sha_cannot_open_passing_baseline(owned):
    class WrongTask(Runner):
        def __call__(self, command, **kwargs):
            result = super().__call__(command, **kwargs)
            if command[0] == "powershell.exe":
                value = json.loads(result.stdout)
                value["action_sha"] = "f" * 40
                result.stdout = json.dumps(value)
            return result
    assert invoke(owned, runner=WrongTask(datetime(2026, 10, 16, 13, 50, tzinfo=ZONE)))["state"] == "UNKNOWN"


def test_summary_cannot_reuse_an_old_release_acceptance(owned):
    folder = owned / "receipts" / "stability"
    folder.mkdir(parents=True)
    for day in ("2026-10-14", "2026-10-15"):
        (folder / f"{day}.json").write_text(json.dumps({
            "report_version": REPORT_VERSION, "session": day, "state": "PASS",
            "calendar": {"verified": True, "is_trade_day": True},
            "identity": {"source_sha": "f" * 40, "config_hash": CONFIG,
                         "image_id": IMAGE, "scope_hash": SCOPE}}), encoding="utf-8")
    result = invoke(owned, "summary")
    assert result["state"] == "PARTIAL"
    assert result["verified_trade_days"] == []
