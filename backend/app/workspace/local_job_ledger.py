"""Local scheduling evidence; independent of the research/account database.

The caller must hold LocalRunLock for execution and crash recovery. SQLite
transactions are short and never span collection, calculation or HTTP calls.
A delivery receipt proves acceptance, never a rendered website consumer.
"""
from __future__ import annotations

import json
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime, time, timezone
from pathlib import Path
from uuid import uuid4

from app.workspace.local_schedule import LOCAL_SCHEDULE_SLOTS, SHANGHAI
from app.workspace.shadow_bundle import digest
from app.workspace.shadow_client import _validate_receipt

VERSION = "local-job-ledger-v1"
TERMINAL_SLOTS = {"DELIVERED", "SUPERSEDED", "MISSED", "FAILED_DELIVERY"}
DETAIL_FIELDS = {"coverage_complete", "requested", "completed", "missing", "failed_count",
                 "degraded_count", "accepted_closed_session", "source_task_status", "execution_mode",
                 "duration_seconds", "latency_seconds", "reason", "error_type", "run_id",
                 "target_trade_date", "scope_hash"}


def _clock(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timezone-aware clock required")
    return value.astimezone(timezone.utc)


def _identity(value: dict) -> dict:
    if not isinstance(value, dict) or set(value) != {"code_sha", "config_hash", "scope_hash"}:
        raise ValueError("exact source/config/scope identity required")
    for key, length in (("code_sha", 40), ("config_hash", 64), ("scope_hash", 64)):
        if not isinstance(value[key], str) or not re.fullmatch(r"[0-9a-f]{%d}" % length, value[key]):
            raise ValueError("invalid scheduling identity")
    if set(value["code_sha"]) == {"0"}:
        raise ValueError("nonzero source identity required")
    return dict(value)


def _json(value) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":"))


def _forward(row, current: datetime) -> None:
    if row is not None and current < datetime.fromisoformat(row["updated_at"]):
        raise ValueError("clock moved backwards during attempt")


class LocalJobLedger:
    def __init__(self, root: Path):
        self.root = Path(root).absolute()
        self.path = self.root / "state" / "schedule.sqlite3"
        self._check_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._transaction() as db:
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, 1):
                raise ValueError("unsupported local ledger schema")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS slots (
                    slot_id TEXT PRIMARY KEY, session TEXT NOT NULL, slot TEXT NOT NULL,
                    status TEXT NOT NULL, planned_at TEXT NOT NULL, updated_at TEXT NOT NULL, reason TEXT);
                CREATE TABLE IF NOT EXISTS attempts (
                    attempt_id TEXT PRIMARY KEY, slot_id TEXT NOT NULL REFERENCES slots(slot_id),
                    attempt_no INTEGER NOT NULL, status TEXT NOT NULL, started_at TEXT NOT NULL,
                    finished_at TEXT, updated_at TEXT NOT NULL, code_sha TEXT NOT NULL,
                    config_hash TEXT NOT NULL, scope_hash TEXT NOT NULL, bundle_file TEXT,
                    sequence INTEGER, bundle_id TEXT, expires_at TEXT, receipt TEXT, reason TEXT,
                    UNIQUE(slot_id, attempt_no));
                CREATE TABLE IF NOT EXISTS jobs (
                    attempt_id TEXT NOT NULL REFERENCES attempts(attempt_id), job_name TEXT NOT NULL,
                    status TEXT NOT NULL, started_at TEXT NOT NULL, finished_at TEXT,
                    run_id TEXT, required INTEGER NOT NULL, details TEXT NOT NULL,
                    PRIMARY KEY(attempt_id, job_name));
                CREATE TABLE IF NOT EXISTS clock_watermark (
                    singleton INTEGER PRIMARY KEY CHECK(singleton=1), observed_at TEXT NOT NULL);
                PRAGMA user_version=1;
            """)

    def _check_path(self):
        for path in (self.root, self.path.parent, self.path):
            if path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction()):
                raise ValueError("ledger paths must not be symlinks or junctions")
        if not self.path.resolve().is_relative_to(self.root.resolve()):
            raise ValueError("ledger path escapes owned root")
        if self.path.exists() and not self.path.is_file():
            raise ValueError("ledger target must be a regular file")

    @contextmanager
    def _transaction(self):
        self._check_path()
        db = sqlite3.connect(self.path, timeout=5)
        db.row_factory = sqlite3.Row
        try:
            db.execute("PRAGMA foreign_keys=ON")
            db.execute("PRAGMA synchronous=FULL")
            db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def _row(row):
        if row is None:
            return None
        result = dict(row)
        for field in ("receipt", "details"):
            if field in result and result[field] is not None:
                result[field] = json.loads(result[field])
        if "required" in result:
            result["required"] = bool(result["required"])
        return result

    @staticmethod
    def _observe_clock(db, current: datetime) -> None:
        previous = db.execute("SELECT observed_at FROM clock_watermark WHERE singleton=1").fetchone()
        if previous is not None and current < datetime.fromisoformat(previous["observed_at"]):
            raise ValueError("clock rollback blocked by durable ledger watermark")
        db.execute("INSERT INTO clock_watermark VALUES(1,?) ON CONFLICT(singleton) DO UPDATE SET observed_at=excluded.observed_at",
                   (current.isoformat(),))

    @staticmethod
    def _finish_export(db, row, *, attempt_status: str, slot_status: str, reason: str, stamp: str) -> None:
        db.execute("UPDATE attempts SET status=?,finished_at=?,updated_at=?,reason=? WHERE attempt_id=? AND status='EXPORTED'",
                   (attempt_status, stamp, stamp, reason, row["attempt_id"]))
        db.execute("UPDATE slots SET status=?,updated_at=?,reason=? WHERE slot_id=? AND status='EXPORTED'",
                   (slot_status, stamp, reason, row["slot_id"]))

    def get_slot(self, slot_id: str) -> dict | None:
        with self._transaction() as db:
            return self._row(db.execute("SELECT * FROM slots WHERE slot_id=?", (slot_id,)).fetchone())

    def get_attempt(self, attempt_id: str) -> dict | None:
        with self._transaction() as db:
            return self._row(db.execute("SELECT * FROM attempts WHERE attempt_id=?", (attempt_id,)).fetchone())

    def plan_due(self, now: datetime, *, verified_trading: bool, identity: dict,
                 slots=LOCAL_SCHEDULE_SLOTS, max_lateness: int = 1200,
                 max_attempts: int = 2, cooldown_seconds: int = 60) -> dict | None:
        current = _clock(now)
        _identity(identity)
        if type(verified_trading) is not bool or not 1 <= max_lateness <= 7200:
            raise ValueError("bounded verified schedule required")
        if not 1 <= max_attempts <= 5 or not 0 <= cooldown_seconds <= 3600:
            raise ValueError("bounded retry policy required")
        if not slots or len(slots) > 32 or len(set(slots)) != len(slots):
            raise ValueError("bounded unique slots required")
        parsed = []
        for slot in slots:
            if not isinstance(slot, str) or not re.fullmatch(r"\d{2}:\d{2}", slot):
                raise ValueError("HH:MM slots required")
            parsed.append((slot, time.fromisoformat(slot)))
        local = current.astimezone(SHANGHAI)
        session = local.date().isoformat()
        stamp = current.isoformat()
        with self._transaction() as db:
            self._observe_clock(db, current)
            # The controller's initial POST + two retries must become terminal
            # before a newer slot can supersede and hide the delivery failure.
            exhausted = db.execute("SELECT a.* FROM attempts a WHERE a.status='EXPORTED' AND "
                                   "(SELECT COUNT(*) FROM jobs j WHERE j.attempt_id=a.attempt_id "
                                   "AND j.status IN ('failed','interrupted') AND "
                                   "(j.job_name='upload' OR j.job_name LIKE 'upload\\_%' ESCAPE '\\')) >= 3").fetchall()
            for attempt in exhausted:
                self._finish_export(db, attempt, attempt_status="FAILED_DELIVERY", slot_status="FAILED_DELIVERY",
                                    reason="upload_retry_budget_exhausted", stamp=stamp)
            db.execute("UPDATE slots SET status='MISSED',reason='previous_session',updated_at=? "
                       "WHERE session<? AND status NOT IN ('DELIVERED','SUPERSEDED','MISSED','FAILED_DELIVERY')", (stamp, session))
            previous_exports = db.execute("SELECT a.* FROM attempts a JOIN slots s ON s.slot_id=a.slot_id "
                                          "WHERE s.session<? AND a.status='EXPORTED'", (session,)).fetchall()
            for attempt in previous_exports:
                self._finish_export(db, attempt, attempt_status="EXPIRED", slot_status="MISSED", reason="previous_session", stamp=stamp)
            if not verified_trading:
                return None
            due = []
            for slot, parsed_time in sorted(parsed):
                sid = f"{session} {slot}"
                planned = datetime.combine(local.date(), parsed_time, SHANGHAI)
                db.execute("INSERT OR IGNORE INTO slots VALUES (?,?,?,'PENDING',?,?,NULL)",
                           (sid, session, slot, planned.astimezone(timezone.utc).isoformat(), stamp))
                age = (local - planned).total_seconds()
                if age >= 0:
                    due.append((sid, age))
            if not due:
                return None
            latest, age = due[-1]
            # Older missed triggers remain explicit evidence, not fake successes.
            for sid, _ in due[:-1]:
                db.execute("UPDATE slots SET status='SUPERSEDED',reason=?,updated_at=? "
                           "WHERE slot_id=? AND status NOT IN ('DELIVERED','SUPERSEDED','MISSED','FAILED_DELIVERY','RUNNING')",
                           (f"newer_slot:{latest}", stamp, sid))
            exported = db.execute("SELECT * FROM attempts WHERE slot_id=? AND status='EXPORTED'", (latest,)).fetchall()
            if age > max_lateness:
                for attempt in exported:
                    self._finish_export(db, attempt, attempt_status="EXPIRED", slot_status="MISSED",
                                        reason="catchup_window_expired", stamp=stamp)
                db.execute("UPDATE slots SET status='MISSED',reason='catchup_window_expired',updated_at=? "
                           "WHERE slot_id=? AND status NOT IN ('DELIVERED','SUPERSEDED','MISSED','FAILED_DELIVERY','RUNNING')",
                           (stamp, latest))
                return None
            for attempt in exported:
                invalid = any(attempt[key] != identity[key] for key in identity)
                expired = datetime.fromisoformat(attempt["expires_at"]) <= current
                if invalid or expired:
                    state = "INVALIDATED" if invalid else "EXPIRED"
                    db.execute("UPDATE attempts SET status=?,updated_at=?,finished_at=?,reason=? WHERE attempt_id=?",
                               (state, stamp, stamp, state.lower(), attempt["attempt_id"]))
                    db.execute("UPDATE slots SET status='FAILED',updated_at=?,reason=? WHERE slot_id=? AND status='EXPORTED'",
                               (stamp, state.lower(), latest))
            row = db.execute("SELECT * FROM slots WHERE slot_id=?", (latest,)).fetchone()
            if row["status"] in TERMINAL_SLOTS or row["status"] in {"RUNNING", "EXPORTED"}:
                return None
            previous = db.execute("SELECT * FROM attempts WHERE slot_id=? ORDER BY attempt_no DESC LIMIT 1", (latest,)).fetchone()
            if previous is not None:
                if previous["attempt_no"] >= max_attempts:
                    return None
                elapsed = (current - datetime.fromisoformat(previous["updated_at"])).total_seconds()
                if previous["status"] not in {"INVALIDATED", "EXPIRED"} and elapsed < cooldown_seconds:
                    return None
            return self._row(row)

    def claim(self, slot_id: str, now: datetime, *, identity: dict, lock_held: bool,
              max_attempts: int = 2, cooldown_seconds: int = 60, max_lateness: int = 1200) -> dict:
        if lock_held is not True:
            raise ValueError("external run lock must be held")
        ident = _identity(identity)
        current = _clock(now)
        if not 1 <= max_attempts <= 5 or not 0 <= cooldown_seconds <= 3600:
            raise ValueError("bounded retry policy required")
        stamp = current.isoformat()
        with self._transaction() as db:
            self._observe_clock(db, current)
            slot = db.execute("SELECT * FROM slots WHERE slot_id=?", (slot_id,)).fetchone()
            if slot is None or slot["status"] not in {"PENDING", "FAILED", "INTERRUPTED"}:
                raise ValueError("slot is not claimable")
            _forward(slot, current)
            planned = datetime.combine(datetime.fromisoformat(slot["session"]).date(), time.fromisoformat(slot["slot"]), SHANGHAI)
            age = (current - planned).total_seconds()
            if current.astimezone(SHANGHAI).date().isoformat() != slot["session"] or not 0 <= age <= max_lateness:
                raise ValueError("slot is outside bounded current-session window")
            if db.execute("SELECT 1 FROM attempts WHERE status='RUNNING' LIMIT 1").fetchone():
                raise ValueError("an attempt is already running")
            previous = db.execute("SELECT * FROM attempts WHERE slot_id=? ORDER BY attempt_no DESC LIMIT 1", (slot_id,)).fetchone()
            attempt_no = previous["attempt_no"] + 1 if previous else 1
            if attempt_no > max_attempts or (previous and previous["status"] not in {"INVALIDATED", "EXPIRED"}
                    and (current - datetime.fromisoformat(previous["updated_at"])).total_seconds() < cooldown_seconds):
                raise ValueError("retry budget or cooldown")
            aid = uuid4().hex
            db.execute("INSERT INTO attempts(attempt_id,slot_id,attempt_no,status,started_at,updated_at,code_sha,config_hash,scope_hash) "
                       "VALUES (?,?,?,'RUNNING',?,?,?,?,?)", (aid, slot_id, attempt_no, stamp, stamp,
                       ident["code_sha"], ident["config_hash"], ident["scope_hash"]))
            db.execute("UPDATE slots SET status='RUNNING',updated_at=?,reason=NULL WHERE slot_id=?", (stamp, slot_id))
            return self._row(db.execute("SELECT * FROM attempts WHERE attempt_id=?", (aid,)).fetchone())

    def recover_interrupted(self, now: datetime, *, lock_held: bool) -> int:
        if lock_held is not True:
            raise ValueError("external run lock must be held")
        stamp = _clock(now).isoformat()
        with self._transaction() as db:
            self._observe_clock(db, _clock(now))
            rows = db.execute("SELECT attempt_id,slot_id,updated_at FROM attempts WHERE status='RUNNING'").fetchall()
            for row in rows:
                _forward(row, _clock(now))
                db.execute("UPDATE attempts SET status='INTERRUPTED',finished_at=?,updated_at=?,reason='owner_process_ended' WHERE attempt_id=?",
                           (stamp, stamp, row["attempt_id"]))
                db.execute("UPDATE slots SET status='INTERRUPTED',updated_at=?,reason='owner_process_ended' WHERE slot_id=? AND status='RUNNING'",
                           (stamp, row["slot_id"]))
                db.execute("UPDATE jobs SET status='interrupted',finished_at=? WHERE attempt_id=? AND status='running'", (stamp, row["attempt_id"]))
            # The process can die after durable export but during POST. Retain
            # that exact packet and record the ambiguous transmission attempt.
            db.execute("UPDATE jobs SET status='interrupted',finished_at=? WHERE status='running' AND attempt_id IN "
                       "(SELECT attempt_id FROM attempts WHERE status='EXPORTED')", (stamp,))
            return len(rows)

    def record_job(self, attempt_id: str, job_name: str, *, status: str, now: datetime,
                   run_id: str | None = None, required: bool = True, details: dict | None = None) -> None:
        stamp = _clock(now).isoformat()
        if not isinstance(job_name, str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,79}", job_name):
            raise ValueError("invalid job name")
        if status not in {"running", "succeeded", "partial", "failed", "unavailable", "interrupted"} or type(required) is not bool:
            raise ValueError("invalid job status")
        details = details or {}
        if not isinstance(details, dict) or not set(details) <= DETAIL_FIELDS:
            raise ValueError("non-public job detail field")
        encoded = _json(details)
        if len(encoded.encode()) > 4096 or any(isinstance(v, (dict, list)) for v in details.values()):
            raise ValueError("bounded scalar job details required")
        if run_id is not None and (not isinstance(run_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", run_id)):
            raise ValueError("invalid task run identity")
        with self._transaction() as db:
            self._observe_clock(db, _clock(now))
            attempt = db.execute("SELECT status,updated_at FROM attempts WHERE attempt_id=?", (attempt_id,)).fetchone()
            _forward(attempt, _clock(now))
            old = db.execute("SELECT * FROM jobs WHERE attempt_id=? AND job_name=?", (attempt_id, job_name)).fetchone()
            upload_job = job_name == "upload" or job_name.startswith("upload_")
            allowed = (attempt is not None and (attempt["status"] == "RUNNING"
                       or (upload_job and attempt["status"] == "EXPORTED")
                       or (upload_job and attempt["status"] == "DELIVERED" and old is not None
                           and old["status"] in {"running", "succeeded"} and status == "succeeded")))
            if not allowed:
                raise ValueError("job requires an active attempt")
            end = None if status == "running" else stamp
            if old is not None:
                if old["run_id"] != run_id or old["required"] != bool(required):
                    raise ValueError("job identity is immutable")
                if old["status"] != "running":
                    if old["status"] == status and old["details"] == encoded:
                        return
                    raise ValueError("terminal job cannot regress")
                db.execute("UPDATE jobs SET status=?,finished_at=?,details=? WHERE attempt_id=? AND job_name=?",
                           (status, end, encoded, attempt_id, job_name))
            else:
                db.execute("INSERT INTO jobs VALUES (?,?,?,?,?,?,?,?)", (attempt_id, job_name, status, stamp, end, run_id, bool(required), encoded))

    def mark_export(self, attempt_id: str, *, manifest: dict, bundle_file: str, now: datetime) -> None:
        current = _clock(now)
        if not isinstance(manifest, dict) or manifest.get("contract_version") != "local-display-v2":
            raise ValueError("display v2 manifest required")
        seq = manifest.get("sequence")
        if type(seq) is not int or seq < 1 or not isinstance(bundle_file, str) or bundle_file != f"bundle_{seq}.json":
            raise ValueError("immutable local bundle basename required")
        expiry = _clock(datetime.fromisoformat(manifest["expires_at"]))
        if expiry <= current:
            raise ValueError("cannot export expired bundle")
        bid = digest(manifest)
        stamp = current.isoformat()
        with self._transaction() as db:
            self._observe_clock(db, current)
            row = db.execute("SELECT * FROM attempts WHERE attempt_id=?", (attempt_id,)).fetchone()
            if row is None or row["status"] not in {"RUNNING", "EXPORTED"}:
                raise ValueError("attempt is not exportable")
            _forward(row, current)
            if row["code_sha"] != manifest.get("code_sha") or row["config_hash"] != manifest.get("config_hash"):
                raise ValueError("export source/config identity mismatch")
            universe = manifest.get("universe")
            if (not isinstance(universe, list) or not universe or not all(isinstance(code, str) for code in universe)
                    or len(set(universe)) != len(universe) or digest(sorted(universe)) != row["scope_hash"]):
                raise ValueError("export scope identity mismatch")
            if row["status"] == "EXPORTED":
                if row["bundle_id"] == bid and row["bundle_file"] == bundle_file:
                    return
                raise ValueError("exported bundle is immutable")
            db.execute("UPDATE attempts SET status='EXPORTED',updated_at=?,bundle_file=?,sequence=?,bundle_id=?,expires_at=? WHERE attempt_id=?",
                       (stamp, bundle_file, seq, bid, expiry.isoformat(), attempt_id))
            db.execute("UPDATE slots SET status='EXPORTED',updated_at=? WHERE slot_id=?", (stamp, row["slot_id"]))

    def mark_delivered(self, attempt_id: str, *, manifest: dict, receipt: dict, now: datetime) -> None:
        stamp = _clock(now).isoformat()
        _validate_receipt(receipt, manifest, "local-display-v2")
        bid = digest(manifest)
        with self._transaction() as db:
            self._observe_clock(db, _clock(now))
            row = db.execute("SELECT * FROM attempts WHERE attempt_id=?", (attempt_id,)).fetchone()
            if row is None or row["status"] not in {"EXPORTED", "DELIVERED"} or row["bundle_id"] != bid:
                raise ValueError("receipt does not bind exported attempt")
            _forward(row, _clock(now))
            if row["status"] == "DELIVERED":
                return
            db.execute("UPDATE attempts SET status='DELIVERED',finished_at=?,updated_at=?,receipt=? WHERE attempt_id=?",
                       (stamp, stamp, _json(receipt), attempt_id))
            db.execute("UPDATE jobs SET status='succeeded',finished_at=? WHERE attempt_id=? AND status='running' "
                       "AND (job_name='upload' OR job_name LIKE 'upload\\_%' ESCAPE '\\')", (stamp, attempt_id))
            db.execute("UPDATE slots SET status='DELIVERED',updated_at=?,reason=NULL WHERE slot_id=? AND status='EXPORTED'", (stamp, row["slot_id"]))

    def fail(self, attempt_id: str, *, reason: str, now: datetime) -> None:
        stamp = _clock(now).isoformat()
        if not isinstance(reason, str) or not re.fullmatch(r"[A-Za-z0-9_. -]{1,120}", reason):
            raise ValueError("bounded public failure reason required")
        with self._transaction() as db:
            self._observe_clock(db, _clock(now))
            row = db.execute("SELECT * FROM attempts WHERE attempt_id=?", (attempt_id,)).fetchone()
            if row is None or row["status"] not in {"RUNNING", "EXPORTED"}:
                raise ValueError("terminal attempt cannot fail")
            _forward(row, _clock(now))
            # An export survives a transport failure and is replayed byte-for-byte.
            status = "EXPORTED" if row["status"] == "EXPORTED" else "FAILED"
            db.execute("UPDATE attempts SET status=?,finished_at=?,updated_at=?,reason=? WHERE attempt_id=?",
                       (status, None if status == "EXPORTED" else stamp, stamp, reason, attempt_id))
            db.execute("UPDATE jobs SET status='failed',finished_at=? WHERE attempt_id=? AND status='running'", (stamp, attempt_id))
            db.execute("UPDATE slots SET status=?,updated_at=?,reason=? WHERE slot_id=? AND status NOT IN ('DELIVERED','SUPERSEDED','MISSED','FAILED_DELIVERY')",
                       (status, stamp, reason, row["slot_id"]))

    def pending_replay(self, *, now: datetime, identity: dict, max_retries: int = 2,
                       cooldown_seconds: int = 60, max_lateness: int = 1200) -> dict | None:
        current = _clock(now)
        ident = _identity(identity)
        if not 0 <= max_retries <= 4 or not 0 <= cooldown_seconds <= 3600 or not 1 <= max_lateness <= 7200:
            raise ValueError("bounded upload retry policy required")
        with self._transaction() as db:
            self._observe_clock(db, current)
            rows = db.execute("SELECT a.* FROM attempts a JOIN slots s ON s.slot_id=a.slot_id "
                              "WHERE a.status='EXPORTED' AND s.status='EXPORTED' ORDER BY a.sequence DESC").fetchall()
            for row in rows:
                slot = db.execute("SELECT session,planned_at FROM slots WHERE slot_id=?", (row["slot_id"],)).fetchone()
                age = (current - datetime.fromisoformat(slot["planned_at"])).total_seconds()
                if (slot["session"] != current.astimezone(SHANGHAI).date().isoformat()
                        or age > max_lateness or datetime.fromisoformat(row["expires_at"]) <= current):
                    self._finish_export(db, row, attempt_status="EXPIRED", slot_status="MISSED",
                                        reason="delivery_window_expired", stamp=current.isoformat())
                    continue
                uploads = db.execute("SELECT * FROM jobs WHERE attempt_id=? AND (job_name='upload' OR job_name LIKE 'upload\\_%' ESCAPE '\\')",
                                     (row["attempt_id"],)).fetchall()
                failed = [job for job in uploads if job["status"] in {"failed", "interrupted"}]
                if len(failed) >= max_retries + 1:
                    self._finish_export(db, row, attempt_status="FAILED_DELIVERY", slot_status="FAILED_DELIVERY",
                                        reason="upload_retry_budget_exhausted", stamp=current.isoformat())
                    continue
                last_failure = max((job["finished_at"] for job in failed), default=None)
                ready = last_failure is None or (current - datetime.fromisoformat(last_failure)).total_seconds() >= cooldown_seconds
                if (all(row[key] == ident[key] for key in ident) and age >= 0 and ready
                        and not any(job["status"] == "running" for job in uploads)):
                    return self._row(row)
        return None

    def summary(self, session: str | None = None) -> dict:
        with self._transaction() as db:
            suffix = " WHERE session=?" if session else ""
            args = (session,) if session else ()
            slots = [self._row(r) for r in db.execute("SELECT * FROM slots" + suffix + " ORDER BY slot_id", args)]
            attempts = [self._row(r) for r in db.execute("SELECT a.* FROM attempts a JOIN slots s ON s.slot_id=a.slot_id" +
                         (" WHERE s.session=?" if session else "") + " ORDER BY a.started_at,a.attempt_no", args)]
            jobs = [self._row(r) for r in db.execute("SELECT j.* FROM jobs j JOIN attempts a ON a.attempt_id=j.attempt_id "
                    "JOIN slots s ON s.slot_id=a.slot_id" + (" WHERE s.session=?" if session else "") + " ORDER BY j.started_at,j.job_name", args)]
        counts = {}
        for slot in slots:
            counts[slot["status"]] = counts.get(slot["status"], 0) + 1
        return {"ledger_version": VERSION, "slots": slots, "attempts": attempts, "jobs": jobs,
                "counts": counts, "consumer_identity": {"state": "NOT_RUN"}}
