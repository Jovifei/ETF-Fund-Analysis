"""Review-only historical evidence store, independent of realtime acceptance.

No provider, delivery ledger, live pointer, scheduler or production DB is used.
The standalone HTTP factory is in historical_archive_api; this persistence layer
is deliberately not registered in the normal application or CLI.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sqlite3
import stat
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

from app.workspace.local_display_contract import _parse_iso, verify_bundle_integrity
from app.workspace.shadow_bundle import canonical, digest

HEX = re.compile(r"[a-f0-9]{64}")
IDENTIFIER = re.compile(r"[A-Za-z0-9_.:-]{1,128}")
RECEIPT_CONTRACT = "historical-archive-receipt-v1"
EVIDENCE_VERSION = "history-evidence-v1"
STATUSES = {"UNKNOWN", "FAILED_DELIVERY", "SUPERSEDED", "EXPORTED", "QUARANTINED", "MISSED"}
OVERHEAD = 256 * 1024
MAX_EVIDENCE_BYTES = 32 * 1024


def strict_json(raw: bytes) -> Any:
    """Reject ambiguous JSON keys and non-finite numbers before hashing content."""
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result

    def nonfinite(_):
        raise ValueError("non-finite JSON number")

    return json.loads(raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=nonfinite)


def _now(now: datetime | None) -> datetime:
    value = now or datetime.now(UTC)
    if value.tzinfo is None:
        raise ValueError("timezone required")
    return value.astimezone(UTC)


def validate_evidence(value: dict) -> dict:
    """Allow only bounded claims; never persist arbitrary logs, paths or secrets."""
    fields = {"version", "original_delivery_status", "declared_slot", "market_observed_at", "attempts"}
    try:
        if not isinstance(value, dict) or set(value) != fields or value["version"] != EVIDENCE_VERSION:
            raise ValueError
        if value["original_delivery_status"] not in STATUSES:
            raise ValueError
        for name in ("declared_slot", "market_observed_at"):
            if value[name] is not None:
                if not isinstance(value[name], str) or len(value[name]) > 64:
                    raise ValueError
                _parse_iso(value[name])
        attempts = value["attempts"]
        if not isinstance(attempts, list) or len(attempts) > 100:
            raise ValueError
        for item in attempts:
            if not isinstance(item, dict) or set(item) != {"attempted_at", "status", "error_code", "request_id"}:
                raise ValueError
            if not isinstance(item["attempted_at"], str) or len(item["attempted_at"]) > 64:
                raise ValueError
            _parse_iso(item["attempted_at"])
            if item["status"] not in STATUSES:
                raise ValueError
            for key in ("error_code", "request_id"):
                if item[key] is not None and (not isinstance(item[key], str) or not IDENTIFIER.fullmatch(item[key])):
                    raise ValueError
        encoded = canonical(value)
        if len(encoded) > MAX_EVIDENCE_BYTES:
            raise ValueError
        return json.loads(encoded)
    except (ValueError, TypeError, KeyError, RecursionError, OverflowError):
        raise ValueError("invalid archive evidence") from None


def _safe_path(path: Path) -> Path:
    path = Path(os.path.abspath(path))
    if any(part.is_symlink() for part in (path, *path.parents)):
        raise ValueError("symlink archive path rejected")
    return path


@dataclass(frozen=True)
class ArchivePolicy:
    root: Path
    protected_roots: tuple[Path, ...]
    trusted_producers: frozenset[tuple[str, str]] = frozenset()
    max_bytes: int = 128 * 1024 * 1024
    min_free_bytes: int = 1024 * 1024 * 1024
    max_payload_bytes: int = 8 * 1024 * 1024
    max_nonces: int = 3000


class ArchiveStore:
    """Atomic raw bytes + immutable receipt, with a separate bounded nonce ledger.

    Caller-supplied protected roots must include live display/sync, outbox,
    research/transaction databases and local job state. This safeguard supplements
    (does not replace) a dedicated process identity, volume and OS permissions.
    """

    def __init__(self, policy: ArchivePolicy):
        self.policy = policy
        self.root = _safe_path(policy.root)
        if not policy.protected_roots:
            raise ValueError("explicit protected roots required")
        for protected in policy.protected_roots:
            other = _safe_path(protected)
            if self.root == other or self.root in other.parents or other in self.root.parents:
                raise ValueError("archive must be isolated from protected roots")
        for number in (policy.max_bytes, policy.max_payload_bytes, policy.max_nonces):
            if type(number) is not int or number <= 0:
                raise ValueError("invalid archive capacity")
        if (type(policy.min_free_bytes) is not int or policy.min_free_bytes < 0
                or policy.max_bytes < 1024 * 1024 or policy.max_payload_bytes > 64 * 1024 * 1024):
            raise ValueError("invalid archive capacity")
        for code, config in policy.trusted_producers:
            if not re.fullmatch(r"[a-f0-9]{40}", code) or not HEX.fullmatch(config):
                raise ValueError("invalid historical producer identity")
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.database_path = self.root / "history.sqlite3"
        self._check_paths()
        try:
            fd = os.open(self.database_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            pass
        else:
            os.close(fd)
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            version = db.execute("PRAGMA user_version").fetchone()[0]
            tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if version == 0 and not tables:
                self._capacity(OVERHEAD)
                db.execute("CREATE TABLE records (archive_id TEXT PRIMARY KEY, raw_sha TEXT, producer TEXT, "
                           "config_hash TEXT, sequence TEXT, raw BLOB, evidence_hash TEXT NOT NULL, "
                           "receipt TEXT NOT NULL)")
                db.execute("CREATE INDEX producer_sequence ON records(producer,config_hash,sequence)")
                db.execute("CREATE TABLE nonces (key_id TEXT, nonce TEXT, expires REAL NOT NULL, "
                           "PRIMARY KEY(key_id,nonce))")
                db.execute("PRAGMA user_version=1")
            elif version != 1 or tables != {"records", "nonces"}:
                raise ValueError("unrecognized archive schema")
            db.commit()

    def _check_paths(self) -> None:
        _safe_path(self.root)
        for path in self.root.iterdir():
            try:
                info = path.lstat()
            except FileNotFoundError:
                if path.name == "history.sqlite3-journal":
                    continue  # Another archive transaction just committed.
                raise
            if not stat.S_ISREG(info.st_mode) or path.name not in {
                "history.sqlite3", "history.sqlite3-journal"
            }:
                raise ValueError("unsafe isolated archive directory")
            if info.st_nlink != 1:
                raise ValueError("archive hard link rejected")

    def _used_bytes(self) -> int:
        total = 0
        for path in self.root.iterdir():
            try:
                total += path.stat().st_size
            except FileNotFoundError:
                if path.name != "history.sqlite3-journal":
                    raise
        return total

    @contextmanager
    def _connect(self, *, readonly: bool = False):
        self._check_paths()
        target = "file:" + quote(str(self.database_path), safe="/:") + "?mode=ro" if readonly else self.database_path
        db = sqlite3.connect(target, timeout=5, isolation_level=None, uri=readonly)
        try:
            if not readonly:
                db.execute("PRAGMA synchronous=FULL")
                # DELETE journal keeps bytes and receipts in one crash-safe transaction.
                db.execute("PRAGMA journal_mode=DELETE")
                pages = max(1, (self.policy.max_bytes - OVERHEAD) // (2 * 4096))
                db.execute(f"PRAGMA max_page_count={pages}")
            yield db
        finally:
            if db.in_transaction:
                db.rollback()
            db.close()

    def _capacity(self, growth: int) -> None:
        self._check_paths()
        used = self._used_bytes()
        size = self.database_path.stat().st_size
        # Reserve an entire rollback copy plus worst-case new BLOB/index pages.
        reserve = size + 2 * growth + OVERHEAD
        if used + reserve > self.policy.max_bytes or shutil.disk_usage(self.root).free < self.policy.min_free_bytes + reserve:
            raise ValueError("archive capacity unavailable")

    def _before_commit(self, db) -> None:
        """Validate actual allocation while rollback is still possible."""
        logical = db.execute("PRAGMA page_count").fetchone()[0] * db.execute("PRAGMA page_size").fetchone()[0]
        used = self._used_bytes()
        if max(logical, used) > self.policy.max_bytes or shutil.disk_usage(self.root).free < self.policy.min_free_bytes:
            raise ValueError("archive capacity unavailable")

    @staticmethod
    def archive_id(raw: bytes) -> str:
        return hashlib.sha256(b"ETF-HISTORY-ORIGINAL-V1\x00" + raw).hexdigest()

    def reserve_nonce(self, key_id: str, nonce: str, *, expires: float, now: datetime) -> None:
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("DELETE FROM nonces WHERE expires < ?", (_now(now).timestamp(),))
            if db.execute("SELECT 1 FROM nonces WHERE key_id=? AND nonce=?", (key_id, nonce)).fetchone():
                raise ValueError("archive request replay rejected")
            if db.execute("SELECT count(*) FROM nonces").fetchone()[0] >= self.policy.max_nonces:
                raise ValueError("archive nonce capacity unavailable")
            self._capacity(1024)
            db.execute("INSERT INTO nonces VALUES (?,?,?)", (key_id, nonce, expires))
            self._before_commit(db)
            db.commit()

    @staticmethod
    def _base_receipt(archive_id: str, proof: dict, submitter_id: str, now: datetime) -> dict:
        if not isinstance(submitter_id, str) or not IDENTIFIER.fullmatch(submitter_id):
            raise ValueError("invalid archive submitter")
        slot = proof["declared_slot"]
        return {"receipt_contract": RECEIPT_CONTRACT, "archive_id": archive_id,
                "archived_at": now.isoformat(), "submitter_id": submitter_id,
                "raw_sha256": None, "bundle_id": None, "sequence": None,
                "producer_code_sha": None, "producer_config_hash": None,
                "original_generated_at": None, "original_expires_at": None,
                "expired_at_arrival": None, "verified_slot": None,
                "declared_lateness_seconds": (now - _parse_iso(slot)).total_seconds() if slot else None,
                "evidence_level": "UPLOADER_CLAIM", "evidence": proof,
                "original_delivery_status": proof["original_delivery_status"],
                "realtime_acceptance": "UNKNOWN", "reasons": [], "conflicts_with": [],
                "research_only": True, "actionable": False, "calibration_status": "not_calibrated"}

    def ingest(self, raw: bytes, evidence: dict, *, original_sha256: str,
               submitter_id: str, now: datetime | None = None) -> dict:
        now = _now(now)
        proof = validate_evidence(evidence)
        if not isinstance(raw, bytes) or not raw or len(raw) > self.policy.max_payload_bytes:
            raise ValueError("archive payload size rejected")
        if not isinstance(original_sha256, str) or not HEX.fullmatch(original_sha256):
            raise ValueError("invalid original sha256")
        raw_hash = hashlib.sha256(raw).hexdigest()
        identity = self.archive_id(raw)
        reasons = []
        manifest = None
        if raw_hash != original_sha256:
            reasons.append("raw_hash_mismatch")
        else:
            try:
                parsed = strict_json(raw)
                if (not isinstance(parsed, dict) or set(parsed) != {"manifest", "parts"}
                        or not verify_bundle_integrity(parsed)):
                    raise ValueError("invalid bundle")
                manifest = parsed["manifest"]
            except (ValueError, TypeError, KeyError, RecursionError, OverflowError):
                reasons.append("bundle_contract_integrity_or_privacy_rejected")
        if reasons:
            # Rejection audit IDs cannot poison the normal ID for valid originals.
            identity = digest({"domain": "history-rejection-v1", "raw_hash": raw_hash,
                               "claimed_hash": original_sha256, "evidence": proof, "reasons": reasons})
        receipt = self._base_receipt(identity, proof, submitter_id, now)
        receipt.update(raw_sha256=raw_hash, status="REJECTED" if reasons else "ARCHIVED", reasons=reasons)
        producer = config = sequence = None
        if manifest is not None:
            producer, config, sequence = manifest["code_sha"], manifest["config_hash"], str(manifest["sequence"])
            receipt.update(bundle_id=digest(manifest), sequence=manifest["sequence"],
                           producer_code_sha=producer, producer_config_hash=config,
                           original_generated_at=manifest["generated_at"], original_expires_at=manifest["expires_at"],
                           expired_at_arrival=now >= _parse_iso(manifest["expires_at"]))
            if (producer, config) not in self.policy.trusted_producers:
                reasons.append("unknown_historical_producer")
            if _parse_iso(manifest["generated_at"]) > now:
                reasons.append("generated_in_future")
            if proof["declared_slot"] and _parse_iso(proof["declared_slot"]) > now:
                reasons.append("declared_slot_in_future")
            if proof["market_observed_at"] and _parse_iso(proof["market_observed_at"]) > _parse_iso(manifest["generated_at"]):
                reasons.append("declared_observation_after_generation")
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute("SELECT evidence_hash,receipt FROM records WHERE archive_id=?", (identity,)).fetchone()
            if existing:
                if existing[0] != digest(proof):
                    raise ValueError("archive evidence_conflict")
                return json.loads(existing[1])
            if manifest is not None:
                conflicts = [row[0] for row in db.execute(
                    "SELECT archive_id FROM records WHERE producer=? AND config_hash=? AND sequence=? "
                    "AND raw IS NOT NULL ORDER BY archive_id", (producer, config, sequence))]
                if conflicts:
                    reasons.append("producer_sequence_conflict")
                receipt["conflicts_with"] = conflicts
                if reasons:
                    receipt["status"] = "QUARANTINED"
            encoded = canonical(receipt)
            payload = raw if manifest is not None else None
            self._capacity(len(encoded) + (len(payload) if payload else 0) + 4096)
            db.execute("INSERT INTO records VALUES (?,?,?,?,?,?,?,?)",
                       (identity, raw_hash, producer, config, sequence, payload, digest(proof), encoded.decode()))
            self._before_commit(db)
            db.commit()
        return receipt

    def record_gap(self, evidence: dict, *, reason: str, submitter_id: str, now: datetime | None = None) -> dict:
        proof = validate_evidence(evidence)
        if reason not in {"original_missing", "original_unreadable", "evidence_missing"}:
            raise ValueError("invalid archive gap reason")
        identity = digest({"domain": "history-gap-v1", "evidence": proof, "reason": reason})
        receipt = self._base_receipt(identity, proof, submitter_id, _now(now))
        receipt.update(status="GAP_RECORDED", reasons=[reason])
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute("SELECT receipt FROM records WHERE archive_id=?", (identity,)).fetchone()
            if existing:
                return json.loads(existing[0])
            encoded = canonical(receipt)
            self._capacity(len(encoded) + 4096)
            db.execute("INSERT INTO records VALUES (?,?,?,?,?,?,?,?)",
                       (identity, None, None, None, None, None, digest(proof), encoded.decode()))
            self._before_commit(db)
            db.commit()
        return receipt

    def get_receipt(self, archive_id: str) -> dict:
        if not isinstance(archive_id, str) or not HEX.fullmatch(archive_id):
            raise ValueError("invalid archive id")
        with self._connect(readonly=True) as db:
            row = db.execute("SELECT receipt FROM records WHERE archive_id=?", (archive_id,)).fetchone()
        return json.loads(row[0]) if row else {"archive_id": archive_id, "status": "UNKNOWN", "realtime_acceptance": "UNKNOWN"}

    def read_original(self, archive_id: str) -> bytes | None:
        if not isinstance(archive_id, str) or not HEX.fullmatch(archive_id):
            raise ValueError("invalid archive id")
        with self._connect(readonly=True) as db:
            row = db.execute("SELECT raw,raw_sha FROM records WHERE archive_id=?", (archive_id,)).fetchone()
        if not row or row[0] is None:
            return None
        if hashlib.sha256(row[0]).hexdigest() != row[1] or self.archive_id(row[0]) != archive_id:
            raise ValueError("archived original integrity failure")
        return row[0]
