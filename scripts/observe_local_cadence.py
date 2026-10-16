"""Read-only, bounded observations for two real trading-session acceptance.

Uses the owner's existing SSH alias, an audited read-only PostgreSQL capture
helper, selected Docker metadata and Windows task metadata. No deployment,
database writes, event-history inference, credentials or automatic retries.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from datetime import date, datetime, time as day_time, timezone
from pathlib import Path, PurePosixPath
from uuid import uuid4

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.services.trading_calendar_service import TradingCalendarService
from app.core.config import Settings
from app.workspace.local_job_ledger import LocalJobLedger
from app.workspace.local_schedule import LocalRunLock, SHANGHAI
from app.workspace.local_stability import (
    METRICS, _cloud, assess_session, record_stability, summarize_stability,
)

DOWNLOAD_ROOT = Path(r"E:\Claude_allow\Download")
REMOTE_DIRECTORY = PurePosixPath("/opt/china-fund-decision/release-phase1-final-9fe9fe8-20261015")
REMOTE_HELPER = str(REMOTE_DIRECTORY / "capture_research_counts_host36_v3.py")
SSH_OPTIONS = ["-o", "BatchMode=yes", "-o", "ConnectTimeout=10"]
NATURAL_TRIGGER = {"state": "NOT_RUN", "reason": "task operational metadata is not Windows task-history proof"}

# Docker emits only these fields and exactly three allowlisted environment keys.
# Neither complete inspect JSON, healthcheck output nor Config.Env is printed.
RUNTIME_PROGRAM = r'''
import datetime,json,subprocess
names=[('api','etf-workspace-v108-production-api'),('worker','etf-workspace-v108-production-worker'),('scheduler','etf-workspace-v108-production-scheduler')]
keys=('GIT_COMMIT_SHA','SCHEDULER_ENABLED','WORKSPACE_RESEARCH_SOURCE')
template='{"state":{{json .State.Status}},"started_at":{{json .State.StartedAt}},"restart_count":{{json .RestartCount}},"oom_killed":{{json .State.OOMKilled}},"image_id":{{json .Image}},"health":{{if .State.Health}}{{json .State.Health.Status}}{{else}}null{{end}},"healthcheck_test":{{if .Config.Healthcheck}}{{json .Config.Healthcheck.Test}}{{else}}null{{end}}}{{printf "\\n"}}'
tests=['(eq (printf "%%.%ds" .) "%s=")' % (len(key)+1,key) for key in keys]
template+='{{range .Config.Env}}{{if or '+' '.join(tests)+'}}{{json .}}{{printf "\\n"}}{{end}}{{end}}'
services=[]
sources=[]
for role,name in names:
    result=subprocess.run(['docker','inspect','--format',template,name],stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=25)
    if result.returncode: raise RuntimeError('runtime inspection failed')
    lines=result.stdout.decode('utf-8').strip().splitlines()
    value=json.loads(lines[0]); env={}
    for line in lines[1:]:
        key,item=json.loads(line).split('=',1)
        if key not in keys or key in env: raise RuntimeError('invalid selected metadata')
        env[key]=item
    source=env.get('GIT_COMMIT_SHA','')
    if len(source)!=40: raise RuntimeError('source metadata missing')
    sources.append(source)
    enabled=env.get('SCHEDULER_ENABLED','').lower()
    value['scheduler_enabled']=False if enabled=='false' else True if enabled=='true' else None
    value['workspace_research_source']=env.get('WORKSPACE_RESEARCH_SOURCE')
    value['role']=role
    if role=='scheduler' and value['healthcheck_test']==['NONE']:
        value['health']='disabled'
    value.pop('healthcheck_test')
    services.append(value)
if len(set(sources))!=1: raise RuntimeError('mixed source metadata')
print(json.dumps({'captured_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'source_sha':sources[0],'services':services}))
'''

TASK_PROGRAM = r'''
$ErrorActionPreference='Stop'
$task=Get-ScheduledTask -TaskName 'ETF-Local-Live-Compute'
$info=$task | Get-ScheduledTaskInfo
$actionSha=$null
if ($task.Actions.Count -eq 1 -and $task.Actions[0].Arguments -match '--expected-sha\s+([a-f0-9]{40})(?:\s|$)') {$actionSha=$Matches[1]}
[ordered]@{task_name='ETF-Local-Live-Compute';state=[string]$task.State;last_result=$info.LastTaskResult;last_run_at=$info.LastRunTime.ToString('o');next_run_at=$info.NextRunTime.ToString('o');action_sha=$actionSha}|ConvertTo-Json -Compress
'''


class ObservationError(Exception):
    """Only constant, public reason codes are passed here."""


def _safe_path(path: Path) -> Path:
    path = path.absolute()
    for current in (path, *path.parents):
        if current.is_symlink() or (hasattr(current, "is_junction") and current.is_junction()):
            raise ValueError("owned non-reparse path required")
    return path


def _json(text: str):
    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ObservationError("duplicate_observation_field")
            value[key] = item
        return value
    def nonfinite(_):
        raise ObservationError("nonfinite_observation")
    value = json.loads(text, object_pairs_hook=unique, parse_constant=nonfinite)
    if not isinstance(value, dict):
        raise ObservationError("observation_object_required")
    return value


def _read(path: Path) -> dict:
    if _safe_path(path).stat().st_size > 1024 * 1024:
        raise ObservationError("observation_input_over_budget")
    return _json(path.read_text(encoding="utf-8-sig"))


def _immutable(path: Path, value: dict) -> None:
    _safe_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True).encode("utf-8")
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())


def _run(command: list[str], *, runner, deadline: float, input: str | None = None):
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise ObservationError("capture_deadline_exceeded")
    result = runner(command, input=input, text=True, capture_output=True,
                    timeout=min(110, remaining), check=False)
    if result.returncode:
        raise ObservationError("observation_command_failed")
    if len(result.stdout.encode("utf-8")) > 1024 * 1024:
        raise ObservationError("observation_output_over_budget")
    return result.stdout


def _capture(mode, session, *, runner, deadline):
    response = _json(_run(["ssh", *SSH_OPTIONS, "aliyun-etf", "python3", REMOTE_HELPER, mode],
                          runner=runner, deadline=deadline))
    receipt = response.get("receipt")
    pattern = re.escape(str(REMOTE_DIRECTORY)) + rf"/research-counts-{mode}-[0-9]+\.json"
    if (response.get("readonly") is not True or response.get("tables") != 14
            or not isinstance(receipt, str) or re.fullmatch(pattern, receipt) is None):
        raise ObservationError("unapproved_cloud_receipt")
    download = _safe_path(DOWNLOAD_ROOT / f"ETF-cadence-observation-{session.isoformat()}")
    download.mkdir(parents=True, exist_ok=True)
    target = download / f"{mode}-{uuid4().hex}.json"
    _run(["scp", *SSH_OPTIONS, f"aliyun-etf:{receipt}", str(target)], runner=runner, deadline=deadline)
    cloud = _read(target)
    _cloud(cloud)
    # Strip unknown fields rather than copying an arbitrary input into F: receipts.
    cloud = {key: cloud[key] for key in ("captured_at", "transaction_read_only", "transaction_isolation",
                                        "database_oid", "server_start", "stats_reset", "schema_heads", "tables")}
    cloud["tables"] = [{key: row[key] for key in ("table_name", *METRICS)} for row in cloud["tables"]]
    runtime = _json(_run(["ssh", *SSH_OPTIONS, "aliyun-etf", "python3", "-"],
                        runner=runner, deadline=deadline, input=RUNTIME_PROGRAM))
    task = _json(_run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", TASK_PROGRAM],
                     runner=runner, deadline=deadline))
    runtime = {key: runtime[key] for key in ("captured_at", "source_sha", "services")}
    service_keys = ("role", "image_id", "state", "health", "restart_count", "oom_killed", "started_at",
                    "scheduler_enabled", "workspace_research_source")
    runtime["services"] = [{key: row[key] for key in service_keys} for row in runtime["services"]]
    task = {key: task[key] for key in ("task_name", "state", "last_result", "last_run_at", "next_run_at", "action_sha")}
    return {"cloud": cloud, "runtime": runtime, "windows_task": task,
            "cloud_capture_sha256": hashlib.sha256(target.read_bytes()).hexdigest()}


def load_ledger(root: Path, session: date) -> dict:
    if not _safe_path(root / "state" / "schedule.sqlite3").is_file():
        raise ObservationError("ledger_missing")
    return LocalJobLedger(root).summary(session.isoformat())


def _summary(root: Path, identity: dict) -> dict:
    reports = []
    folder = _safe_path(root / "receipts" / "stability")
    for path in sorted(folder.glob("*.json")):
        report = _read(path)
        if report.get("identity") == identity:
            reports.append(report)
    return {**summarize_stability(reports), "identity": identity, "natural_trigger": NATURAL_TRIGGER}


def observe(*, mode: str, root: Path, session: date, expected_source_sha: str,
            expected_config_hash: str, expected_image_id: str, expected_scope_hash: str | None = None,
            calendar=None, now=lambda: datetime.now(timezone.utc), runner=subprocess.run) -> dict:
    root = _safe_path(Path(root))
    if not _safe_path(root / ".local-live").is_file():
        raise ValueError("owned .local-live root required")
    identity = {"source_sha": expected_source_sha, "config_hash": expected_config_hash,
                "image_id": expected_image_id, "scope_hash": expected_scope_hash}
    if (re.fullmatch(r"[0-9a-f]{40}", expected_source_sha) is None
            or re.fullmatch(r"[0-9a-f]{64}", expected_config_hash) is None
            or re.fullmatch(r"sha256:[0-9a-f]{64}", expected_image_id) is None
            or (expected_scope_hash is not None and re.fullmatch(r"[0-9a-f]{64}", expected_scope_hash) is None)):
        raise ValueError("fixed observation identities required")
    if mode == "summary":
        return _summary(root, identity)
    if mode not in {"before", "after"}:
        raise ValueError("before/after/summary mode required")
    current = now()
    if current.tzinfo is None:
        raise ValueError("observation clock requires timezone")
    local = current.astimezone(SHANGHAI)
    folder = _safe_path(root / "receipts" / "stability-observations" / session.isoformat())
    attempt = {"mode": mode, "session": session.isoformat(), "attempt_id": uuid4().hex,
               "started_at": current.isoformat(), "state": "PARTIAL", "identity": identity,
               "natural_trigger": NATURAL_TRIGGER}
    lock = LocalRunLock(_safe_path(root / ".stability-observer.lock"))
    if not lock.acquire():
        return {**attempt, "reason": "observer_already_running"}
    try:
        decision = (calendar or TradingCalendarService(Settings(_env_file=None))).decision(session)
        if local.date() != session or not decision.verified or not decision.is_trade_day:
            raise ObservationError("verified_current_trading_session_required")
        lower, upper = (day_time(13, 50), day_time(13, 55)) if mode == "before" else (day_time(16, 30), day_time(17))
        if not lower <= local.time() < upper:
            raise ObservationError("observation_window_missed")
        saved = folder / f"{mode}.json"
        if mode == "after" and not (folder / "before.json").is_file():
            raise ObservationError("before_capture_missing")
        if saved.exists():
            capture = _read(saved)
            if capture.get("identity") != identity:
                raise ObservationError("capture_identity_mismatch")
            if mode == "before":
                return {**attempt, "state": "ALREADY_CAPTURED"}
        else:
            capture = _capture(mode, session, runner=runner, deadline=time.monotonic() + 120)
            runtime = capture["runtime"]
            if runtime.get("source_sha") != expected_source_sha or capture["windows_task"].get("action_sha") != expected_source_sha:
                raise ObservationError("runtime_or_task_source_mismatch")
            if len(runtime["services"]) != 3 or {row["role"] for row in runtime["services"]} != {"api", "worker", "scheduler"}:
                raise ObservationError("runtime_roles_missing")
            for row in runtime["services"]:
                if (row["image_id"] != expected_image_id or row["state"] != "running"
                        or row["health"] != ("disabled" if row["role"] == "scheduler" else "healthy")
                        or type(row["restart_count"]) is not int or row["restart_count"] != 0 or row["oom_killed"] is not False
                        or row["scheduler_enabled"] is not False or row["workspace_research_source"] != "local_bundle"):
                    raise ObservationError("runtime_not_expected_healthy_read_only")
            capture.update(identity=identity, session=session.isoformat(), mode=mode,
                           natural_trigger=NATURAL_TRIGGER)
            _immutable(saved, capture)
        if mode == "before":
            attempt["state"] = "CAPTURED"
        else:
            before = _read(folder / "before.json")
            if before.get("identity") != identity:
                raise ObservationError("baseline_identity_mismatch")
            report = assess_session(session=session, ledger_summary=load_ledger(root, session),
                cloud_before=before["cloud"], cloud_after=capture["cloud"],
                runtime_before=before["runtime"], runtime_after=capture["runtime"],
                expected_source_sha=expected_source_sha, expected_config_hash=expected_config_hash,
                expected_image_id=expected_image_id, expected_scope_hash=expected_scope_hash,
                calendar=calendar, as_of=now())
            report["natural_trigger"] = NATURAL_TRIGGER
            _safe_path(root / "receipts" / "stability" / f"{session.isoformat()}.json")
            record_stability(root, report)
            attempt.update(state=report["state"], two_day_state=_summary(root, identity)["state"],
                           report_file=f"receipts/stability/{session.isoformat()}.json")
    except ObservationError as exc:
        attempt.update(reason=str(exc), state="PARTIAL" if str(exc) in {
            "verified_current_trading_session_required", "observation_window_missed", "before_capture_missing", "ledger_missing"} else "UNKNOWN")
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError):
        attempt.update(state="UNKNOWN", reason="invalid_or_unavailable_observation")
    finally:
        try:
            attempt["finished_at"] = now().isoformat()
            _immutable(folder / "attempts" / f"{attempt['attempt_id']}.json", attempt)
        finally:
            lock.release()
    return attempt


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("before", "after", "summary"))
    parser.add_argument("--root", required=True)
    parser.add_argument("--session", default=None)
    parser.add_argument("--expected-source-sha", required=True)
    parser.add_argument("--expected-config-hash", required=True)
    parser.add_argument("--expected-image-id", required=True)
    parser.add_argument("--expected-scope-hash")
    args = parser.parse_args(argv)
    report = observe(mode=args.mode, root=Path(args.root),
        session=date.fromisoformat(args.session) if args.session else datetime.now(SHANGHAI).date(),
        expected_source_sha=args.expected_source_sha, expected_config_hash=args.expected_config_hash,
        expected_image_id=args.expected_image_id, expected_scope_hash=args.expected_scope_hash)
    print(json.dumps(report, ensure_ascii=False, allow_nan=False))
    return 0 if report["state"] in {"CAPTURED", "ALREADY_CAPTURED", "PASS"} else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, TypeError, KeyError):
        print(json.dumps({"state": "UNKNOWN", "reason": "invalid_or_unavailable_observation"}))
        raise SystemExit(2)
