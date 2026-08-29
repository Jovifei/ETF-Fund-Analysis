"""Private, transient portfolio screenshot import workflow.

The service deliberately keeps image bytes out of the database and keeps the
existing :class:`HoldingService` as the only final holding writer.
"""

from __future__ import annotations

import os
import re
import secrets
import shutil
import stat
import unicodedata
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, object_session, selectinload, sessionmaker

from app.core.config import Settings, get_settings
from app.models import Holding, HoldingImportCandidate, HoldingImportSession, Instrument
from app.ocr.contracts import (
    CandidateField,
    ConfidenceEntry,
    OCRBackend,
    OCRCandidateAction,
    OCRCandidateStatus,
    OCRMatchStatus,
    OCRUnavailable,
)
from app.ocr.image_validation import validate_image_artifact
from app.ocr.paddle_adapter import PaddleOCRAdapter
from app.services.holding_service import HoldingService
from app.utils.canonical_json import validate_safe_text

_TOKEN_RE = re.compile(r"^[0-9a-f]{16,256}$")
_FULL_CODE_RE = re.compile(r"(?<!\d)(?P<symbol>\d{6})\.(?P<exchange>SH|SZ|BJ)(?![A-Z0-9])", re.I)
_ANY_SUFFIX_RE = re.compile(r"(?<!\d)(?P<symbol>\d{6})\.(?P<exchange>[^\s]+)")
_EXPLICIT_SYMBOL_RE = re.compile(r"(?<!\d)(?P<symbol>\d{6})\s*\.?\s*(?P<exchange>SH|SZ|BJ)(?![A-Z0-9])", re.I)
_ANY_SPACED_EXCHANGE_RE = re.compile(r"(?<!\d)(?P<symbol>\d{6})\s+(?P<exchange>[A-Za-z]{2,})\b", re.I)
_SYMBOL_RE = re.compile(r"(?<!\d)(?P<symbol>\d{6})(?!\d)")
_NUMBER_RE = re.compile(r"(?<![\w.])-?\d+(?:\.\d+)?(?![\w.])")
_MIN_CONFIDENCE = 0.75
_MAX_CANDIDATES = 512
_MAX_ALTERNATIVES = 16


@dataclass(frozen=True, slots=True)
class _OCRRow:
    cells: tuple[Any, ...]

    @property
    def text(self) -> str:
        return " ".join(str(cell.text) for cell in self.cells)

    @property
    def confidence(self) -> float:
        return min(float(cell.confidence) for cell in self.cells)


class HoldingImportError(ValueError):
    """Safe, typed workflow error suitable for an API boundary."""

    def __init__(self, code: str, message: str = "holding import rejected") -> None:
        self.code = code
        super().__init__(message)


class HoldingImportNotFound(HoldingImportError):
    def __init__(self) -> None:
        super().__init__("not_found", "holding import session not found")


class HoldingImportConflict(HoldingImportError):
    def __init__(self, code: str = "invalid_state", message: str = "holding import state cannot change") -> None:
        super().__init__(code, message)


class HoldingImportUnavailable(HoldingImportError):
    def __init__(self, code: str = "ocr_unavailable") -> None:
        super().__init__(code, "local OCR is unavailable")


def get_default_ocr_backend(settings: Settings) -> OCRBackend:
    return PaddleOCRAdapter(
        model_dir=settings.ocr_local_model_dir,
        timeout_seconds=settings.ocr_timeout_seconds,
    )


def _now() -> datetime:
    return datetime.now(UTC)


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _normalize_text(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).split())


def _safe_token(value: str) -> str:
    if not isinstance(value, str) or _TOKEN_RE.fullmatch(value) is None:
        raise HoldingImportNotFound()
    return value


def _parse_decimal(value: str, *, maximum: Decimal, scale: int) -> Decimal | None:
    if "," in value or "，" in value:
        return None
    try:
        number = Decimal(value)
    except (InvalidOperation, ValueError):
        return None
    if not number.is_finite() or number < 0 or number > maximum:
        return None
    quantum = Decimal(1).scaleb(-scale)
    if number.quantize(quantum) != number:
        return None
    return number


def _field_confidence(confidence: float, values: dict[str, Any]) -> tuple[ConfidenceEntry, ...]:
    return tuple(
        ConfidenceEntry(field=field, confidence=confidence)
        for field in CandidateField
        if values.get(field.value) is not None
    )


class HoldingImportService:
    def __init__(
        self,
        settings: Settings | None = None,
        *,
        ocr_backend: OCRBackend | None = None,
        holding_service: HoldingService | None = None,
        clock: Any = _now,
        before_claim: Any = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.ocr_backend = ocr_backend or get_default_ocr_backend(self.settings)
        self.holding_service = holding_service or HoldingService()
        self.clock = clock
        self.before_claim = before_claim

    @staticmethod
    def _owned_db(caller_db: Session) -> Session:
        bind = caller_db.get_bind()
        if bind.dialect.name == "sqlite" and getattr(bind.url, "database", None) in {None, ":memory:"}:
            raise HoldingImportConflict("memory_database", "holding import requires a file-backed database")
        if caller_db.new or caller_db.dirty or caller_db.deleted:
            raise HoldingImportConflict(
                "transaction_isolation",
                "holding import requires a clean caller transaction",
            )
        if caller_db.in_transaction() or caller_db.in_nested_transaction():
            raise HoldingImportConflict(
                "transaction_isolation",
                "holding import requires no active caller transaction",
            )
        return sessionmaker(bind=bind, autoflush=False, expire_on_commit=False, class_=Session)()

    @staticmethod
    def _commit(db: Session) -> None:
        db.commit()

    @staticmethod
    def _read_detached(caller_db: Session, session_id: str) -> HoldingImportSession:
        read_db = sessionmaker(bind=caller_db.get_bind(), autoflush=False, expire_on_commit=False, class_=Session)()
        try:
            session = read_db.scalar(
                select(HoldingImportSession)
                .options(selectinload(HoldingImportSession.candidates))
                .where(HoldingImportSession.session_id == session_id)
            )
            if session is None:
                raise HoldingImportNotFound()
            read_db.expunge(session)
            return session
        finally:
            read_db.close()

    @property
    def root(self) -> Path:
        return self.settings.ocr_transient_root.resolve()

    def _session_dir(self, storage_key: str) -> Path:
        key = _safe_token(storage_key)
        root = self.root
        path = (root / key).resolve()
        if path.parent != root or not path.is_relative_to(root):
            raise HoldingImportConflict("storage_path", "holding import storage path rejected")
        return path

    def _remove_storage(self, storage_key: str | None) -> bool:
        if not storage_key:
            return True
        try:
            path = self._session_dir(storage_key)
            if path.is_symlink() or path.is_file():
                path.unlink(missing_ok=True)
            elif path.is_dir():
                shutil.rmtree(path)
            return not path.exists()
        except (OSError, HoldingImportError):
            # Cleanup is best effort; importantly, a malformed key can never
            # broaden this operation beyond the configured transient root.
            return False

    def _finalize_terminal_storage(self, db: Session, session: HoldingImportSession) -> bool:
        """Delete one exact token directory, then persist key clearance.

        Terminal status is committed by the caller before this method runs.
        Missing storage is success; all other filesystem failures retain the
        key so a later startup/request cleanup can retry safely.
        """
        if session.storage_key is None:
            return True
        if not self._remove_storage(session.storage_key):
            return False
        session.storage_key = None
        db.flush()
        self._commit(db)
        return True

    def finalize_storage(self, db_or_session: Session | HoldingImportSession, session: HoldingImportSession | None = None) -> bool:
        """Compatibility helper; service-owned paths pass both DB and row."""
        if session is None:
            if isinstance(db_or_session, HoldingImportSession):
                bound_db = object_session(db_or_session)
                if bound_db is not None:
                    work_db = self._owned_db(bound_db)
                    try:
                        work_session = work_db.scalar(
                            select(HoldingImportSession).where(
                                HoldingImportSession.session_id == db_or_session.session_id
                            )
                        )
                        return work_session is not None and self._finalize_terminal_storage(work_db, work_session)
                    finally:
                        work_db.close()
                removed = self._remove_storage(db_or_session.storage_key)
                if removed:
                    # Detached rows cannot be persisted here; direct service
                    # confirm/cancel always use the bound path above.
                    db_or_session.storage_key = None
                return removed
            raise TypeError("finalize_storage requires a session")
        work_db = self._owned_db(db_or_session)
        try:
            work_session = work_db.scalar(
                select(HoldingImportSession).where(HoldingImportSession.session_id == session.session_id)
            )
            if work_session is None:
                return False
            return self._finalize_terminal_storage(work_db, work_session)
        finally:
            work_db.close()

    def cleanup_expired(self, db: Session, *, now: datetime | None = None) -> int:
        current = _aware(now or self.clock())
        # Never commit or roll back the caller's unit of work. Cleanup is a
        # separate short transaction so request handlers can safely have
        # unrelated pending changes.
        cleanup_db = sessionmaker(bind=db.get_bind(), autoflush=False, expire_on_commit=False, class_=Session)()
        try:
            rows = cleanup_db.scalars(
                select(HoldingImportSession).where(
                    (
                        HoldingImportSession.status.in_(["pending", "processing", "ready", "editing", "confirming", "failed"])
                        & (HoldingImportSession.expires_at < current)
                    )
                    | (
                        HoldingImportSession.status.in_(["confirmed", "cancelled", "expired", "failed"])
                        & HoldingImportSession.storage_key.is_not(None)
                    ),
                )
            ).all()
            expiring = [
                row
                for row in rows
                if row.status in {"pending", "processing", "ready", "editing", "confirming"}
            ]
            for session in expiring:
                session.status = "expired"
            if expiring:
                cleanup_db.flush()
                self._commit(cleanup_db)
            for session in rows:
                self._finalize_terminal_storage(cleanup_db, session)
            return len(rows)
        except OperationalError:
            cleanup_db.rollback()
            return 0
        finally:
            cleanup_db.close()

    def _write_payload(self, storage_key: str, payload: bytes) -> None:
        directory = self._session_dir(storage_key)
        try:
            root = self.root
            root.mkdir(mode=0o700, parents=True, exist_ok=True)
            os.chmod(root, 0o700)
            if os.name != "nt" and stat.S_IMODE(root.stat().st_mode) != 0o700:
                raise OSError("transient root permissions could not be verified")
            os.mkdir(directory, 0o700)
            os.chmod(directory, 0o700)
            if os.name != "nt" and stat.S_IMODE(directory.stat().st_mode) != 0o700:
                raise OSError("transient directory permissions could not be verified")
            path = directory / "source.img"
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as handle:
                handle.write(payload)
                handle.flush()
            os.chmod(path, 0o600)
            if os.name != "nt" and stat.S_IMODE(path.stat().st_mode) != 0o600:
                raise OSError("transient file permissions could not be verified")
        except Exception:
            self._remove_storage(storage_key)
            raise

    @staticmethod
    def _assemble_ocr_rows(lines: tuple[Any, ...]) -> tuple[_OCRRow, ...]:
        """Group nearby OCR boxes into rows, preserving left-to-right cells."""
        rows: list[list[Any]] = []
        for line in lines[:_MAX_CANDIDATES]:
            if line.box is None:
                rows.append([line])
                continue
            ys = [float(point[1]) for point in line.box.points]
            top, bottom = min(ys), max(ys)
            center = (top + bottom) / 2
            height = max(bottom - top, 1.0)
            chosen: list[Any] | None = None
            best_overlap = 0.0
            for row in rows:
                boxed = [item for item in row if item.box is not None]
                if not boxed:
                    continue
                row_ys = [float(point[1]) for item in boxed for point in item.box.points]
                row_top, row_bottom = min(row_ys), max(row_ys)
                overlap = max(0.0, min(bottom, row_bottom) - max(top, row_top))
                row_center = (row_top + row_bottom) / 2
                tolerance = max(height, row_bottom - row_top, 1.0) * 0.5
                if overlap > 0 or abs(center - row_center) <= tolerance:
                    if overlap > best_overlap:
                        best_overlap = overlap
                        chosen = row
            if chosen is None:
                rows.append([line])
            else:
                chosen.append(line)
        ordered: list[_OCRRow] = []
        for row in rows:
            row.sort(
                key=lambda item: (
                    min(float(point[0]) for point in item.box.points) if item.box is not None else 0.0,
                    min(float(point[1]) for point in item.box.points) if item.box is not None else 0.0,
                )
            )
            ordered.append(_OCRRow(tuple(row)))
        ordered.sort(
            key=lambda row: min(
                min(float(point[1]) for point in cell.box.points)
                for cell in row.cells
                if cell.box is not None
            ) if any(cell.box is not None for cell in row.cells) else 0.0
        )
        return tuple(ordered)

    @staticmethod
    def _instrument_maps(db: Session) -> tuple[list[Instrument], dict[str, list[Instrument]], dict[str, list[Instrument]]]:
        instruments = db.scalars(select(Instrument).order_by(Instrument.ts_code)).all()
        by_symbol: dict[str, list[Instrument]] = {}
        by_name: dict[str, list[Instrument]] = {}
        for item in instruments:
            by_symbol.setdefault(str(item.symbol).strip(), []).append(item)
            by_name.setdefault(_normalize_text(item.name).casefold(), []).append(item)
        return instruments, by_symbol, by_name

    @staticmethod
    def _resolve_line(
        by_symbol: dict[str, list[Instrument]],
        by_name: dict[str, list[Instrument]],
        text: str,
        confidence: float,
        seen_codes: set[str],
        existing_codes: set[str],
        cells: tuple[Any, ...] | None = None,
    ) -> HoldingImportCandidate:
        normalized = _normalize_text(text)
        full = _FULL_CODE_RE.search(normalized)
        invalid_explicit = (
            (_ANY_SUFFIX_RE.search(normalized) or _ANY_SPACED_EXCHANGE_RE.search(normalized))
            and not full
        )
        explicit_symbol = _EXPLICIT_SYMBOL_RE.search(normalized)
        symbol_match = _SYMBOL_RE.search(normalized)
        alternatives: list[str] = []
        instrument: Instrument | None = None
        ambiguous = False
        if invalid_explicit:
            # An explicit but unsupported exchange is a user-visible mismatch;
            # never reinterpret its six digits as an exchange-free symbol.
            pass
        elif full:
            code = f"{full.group('symbol')}.{full.group('exchange').upper()}"
            candidates = [item for item in by_symbol.get(full.group("symbol"), []) if item.ts_code.upper() == code]
            if len(candidates) == 1:
                instrument = candidates[0]
            else:
                alternatives = [code]
        elif explicit_symbol:
            exchange = explicit_symbol.group("exchange").upper()
            code = f"{explicit_symbol.group('symbol')}.{exchange}"
            candidates = [item for item in by_symbol.get(explicit_symbol.group("symbol"), []) if item.ts_code.upper() == code]
            if len(candidates) == 1:
                instrument = candidates[0]
            else:
                alternatives = [code]
        elif symbol_match:
            candidates = by_symbol.get(symbol_match.group("symbol"), [])
            if len(candidates) == 1:
                instrument = candidates[0]
            elif len(candidates) > 1:
                ambiguous = True
                alternatives = [item.ts_code for item in candidates[:_MAX_ALTERNATIVES]]
        code_text = _FULL_CODE_RE.sub(" ", normalized)
        code_text = _EXPLICIT_SYMBOL_RE.sub(" ", code_text)
        code_text = _SYMBOL_RE.sub(" ", code_text)
        name_text = _normalize_text(_NUMBER_RE.sub(" ", code_text)).casefold()
        numeric_values: list[str] | None = None
        if cells:
            cell_names = {
                _normalize_text(str(cell.text)).casefold()
                for cell in cells
                if not _FULL_CODE_RE.search(str(cell.text))
                and not _EXPLICIT_SYMBOL_RE.search(str(cell.text))
                and not re.fullmatch(r"\s*-?\d+(?:\.\d+)?\s*", str(cell.text))
            }
            exact_names = [name for name in cell_names if name in by_name]
            if len(exact_names) == 1:
                name_text = exact_names[0]
            elif exact_names:
                name_text = exact_names[0]
            numeric_values = []
            name_seen = False
            for cell in cells:
                cell_text = _normalize_text(str(cell.text))
                if cell_text.casefold() == name_text:
                    name_seen = True
                    continue
                if _FULL_CODE_RE.search(cell_text) or _EXPLICIT_SYMBOL_RE.search(cell_text):
                    continue
                if name_seen or not exact_names:
                    if re.fullmatch(r"\s*-?\d+(?:\.\d+)?\s*", cell_text):
                        numeric_values.extend(_NUMBER_RE.findall(cell_text))
            if not numeric_values:
                numeric_values = None
        if instrument is None and not invalid_explicit and not full and not symbol_match:
            names = by_name.get(name_text, [])
            if len(names) == 1:
                instrument = names[0]
            elif len(names) > 1:
                ambiguous = True
                alternatives = [item.ts_code for item in names[:_MAX_ALTERNATIVES]]

        numbers = numeric_values if numeric_values is not None else _NUMBER_RE.findall(code_text)
        # A dot is the canonical decimal separator here; only grouped comma
        # forms are rejected as locale-ambiguous input.
        invalid_locale = bool(re.search(r"\d[,，]\d{3}(?:\D|$)", code_text))
        shares = _parse_decimal(numbers[0], maximum=Decimal("1000000000"), scale=4) if numbers else None
        cost = _parse_decimal(numbers[1], maximum=Decimal("1000000000"), scale=6) if len(numbers) > 1 else None
        target = _parse_decimal(numbers[2], maximum=Decimal("1"), scale=6) if len(numbers) > 2 else None
        if invalid_locale:
            shares = cost = target = None
        values: dict[str, Any] = {
            "ts_code": instrument.ts_code if instrument else None,
            "name": instrument.name if instrument and _normalize_text(instrument.name).casefold() == name_text else None,
            "shares": shares,
            "cost_price": cost,
            "target_weight": float(target) if target is not None else None,
        }
        hash_text = normalized[:2000]
        import hashlib

        status = OCRMatchStatus.MATCHED.value if instrument else (
            OCRMatchStatus.AMBIGUOUS.value if ambiguous else OCRMatchStatus.UNMATCHED.value
        )
        if confidence < _MIN_CONFIDENCE:
            status = OCRMatchStatus.LOW_CONFIDENCE.value
        elif instrument and (instrument.ts_code in seen_codes or instrument.ts_code in existing_codes):
            status = OCRMatchStatus.DUPLICATE.value
        return HoldingImportCandidate(
            row_index=0,
            ts_code=values["ts_code"],
            name=values["name"],
            shares=shares,
            cost_price=cost,
            target_weight=values["target_weight"],
            match_status=status,
            status=OCRCandidateStatus.PENDING.value,
            action=OCRCandidateAction.NONE.value,
            safe_alternatives_json=alternatives[:_MAX_ALTERNATIVES],
            field_confidence_json=_field_confidence(confidence, values),
            normalized_ocr_text_hash=hashlib.sha256(hash_text.encode("utf-8")).hexdigest(),
        )

    def import_bytes(self, db: Session, payload: bytes, declared_mime: str | None) -> HoldingImportSession:
        work_db = self._owned_db(db)
        try:
            durable = self._import_bytes_owned(work_db, payload, declared_mime)
            session_id = durable.session_id
        finally:
            work_db.close()
        return self._read_detached(db, session_id)

    def _import_bytes_owned(self, db: Session, payload: bytes, declared_mime: str | None) -> HoldingImportSession:
        self.cleanup_expired(db)
        image = validate_image_artifact(
            payload,
            declared_mime=declared_mime,
            max_bytes=self.settings.ocr_max_bytes,
            max_width=self.settings.ocr_max_width,
            max_height=self.settings.ocr_max_height,
            max_pixels=self.settings.ocr_max_pixels,
        )
        if self.settings.ocr_mode == "disabled":
            raise HoldingImportUnavailable("ocr_disabled")
        session_id = secrets.token_hex(32)
        storage_key = secrets.token_hex(32)
        now = _aware(self.clock())
        session = HoldingImportSession(
            session_id=session_id,
            status="processing",
            image_sha256=image.metadata.sha256,
            detected_mime=image.metadata.mime_type,
            image_bytes=image.metadata.byte_size,
            image_width=image.metadata.width,
            image_height=image.metadata.height,
            ocr_mode=self.settings.ocr_mode,
            ocr_backend="local_paddle",
            ocr_model="unavailable",
            ocr_version="unavailable",
            candidate_count=0,
            expires_at=now + timedelta(minutes=self.settings.ocr_transient_ttl_minutes),
            storage_key=storage_key,
        )
        try:
            # Durable phase one: after this commit, a crash can always find
            # the processing row and expire/retry its exact token directory.
            db.add(session)
            db.flush()
            self._commit(db)
        except Exception:
            db.rollback()
            self._remove_storage(storage_key)
            raise
        try:
            # The database row now owns the token before any file is created.
            self._write_payload(storage_key, image.payload)
        except Exception:
            db.rollback()
            durable = db.scalar(select(HoldingImportSession).where(HoldingImportSession.session_id == session_id))
            if durable is not None:
                durable.status = "failed"
                try:
                    db.flush()
                    self._commit(db)
                    self._finalize_terminal_storage(db, durable)
                except Exception:
                    db.rollback()
            raise HoldingImportUnavailable("storage_unavailable") from None
        try:
            result = self.ocr_backend.recognize(image.payload)
            if isinstance(result, OCRUnavailable):
                session.status = "failed"
                session.ocr_backend = result.backend
                session.ocr_model = result.model
                session.ocr_version = result.version
                db.flush()
                self._commit(db)
                self._finalize_terminal_storage(db, session)
                raise HoldingImportUnavailable(result.reason.value)
            session.ocr_backend = result.backend
            session.ocr_model = result.model
            session.ocr_version = result.version
            existing_codes = {
                item.ts_code.upper()
                for item in db.scalars(select(Instrument).join(Holding, Holding.instrument_id == Instrument.id)).all()
            }
            seen_codes: set[str] = set()
            # The maps are read-only during candidate resolution; build them
            # once instead of rescanning all instruments for every OCR row.
            _, by_symbol, by_name = self._instrument_maps(db)
            for index, row in enumerate(self._assemble_ocr_rows(tuple(result.lines))):
                candidate = self._resolve_line(
                    by_symbol, by_name, row.text, row.confidence, seen_codes, existing_codes, row.cells
                )
                candidate.row_index = index
                if candidate.ts_code:
                    seen_codes.add(candidate.ts_code.upper())
                session.candidates.append(candidate)
            session.candidate_count = len(session.candidates)
            session.status = "ready"
            db.flush()
            self._commit(db)
            return session
        except HoldingImportUnavailable:
            raise
        except Exception:
            db.rollback()
            durable = db.scalar(select(HoldingImportSession).where(HoldingImportSession.session_id == session_id))
            if durable is not None:
                durable.status = "failed"
                try:
                    db.flush()
                    self._commit(db)
                    self._finalize_terminal_storage(db, durable)
                except Exception:
                    db.rollback()
                    # Keep durable processing/failed row and source key for a
                    # later cleanup retry; never orphan-delete blindly.
                    pass
            raise HoldingImportUnavailable() from None

    def get(self, db: Session, session_id: str) -> HoldingImportSession:
        self.cleanup_expired(db)
        token = _safe_token(session_id)
        return self._read_detached(db, token)

    @contextmanager
    def _confirm_lock(self, session_id: str):
        del session_id
        # Database CAS below is the sole authority; no process-local lock is
        # used, so independent workers exercise the same correctness path.
        yield

    def edit_candidate(self, db: Session, session_id: str, candidate_id: int, changes: Any) -> HoldingImportCandidate:
        work_db = self._owned_db(db)
        try:
            self._edit_candidate_owned(work_db, session_id, candidate_id, changes)
            self._commit(work_db)
        finally:
            work_db.close()
        read_db = sessionmaker(bind=db.get_bind(), autoflush=False, expire_on_commit=False, class_=Session)()
        try:
            candidate = read_db.get(HoldingImportCandidate, candidate_id)
            if candidate is None:
                raise HoldingImportNotFound()
            read_db.expunge(candidate)
            return candidate
        finally:
            read_db.close()

    def _edit_candidate_owned(self, db: Session, session_id: str, candidate_id: int, changes: Any) -> HoldingImportCandidate:
        token = _safe_token(session_id)
        claim_now = _aware(self.clock())
        changed = db.execute(
            update(HoldingImportSession)
            .execution_options(synchronize_session=False)
            .where(
                HoldingImportSession.session_id == token,
                HoldingImportSession.status == "ready",
                HoldingImportSession.expires_at >= claim_now,
            )
            .values(status="editing")
        ).rowcount
        if changed != 1:
            current = db.scalar(select(HoldingImportSession).where(HoldingImportSession.session_id == token))
            if current is None:
                raise HoldingImportNotFound()
            if current.status == "confirmed":
                raise HoldingImportConflict("confirmed", "confirmed holding import cannot be edited")
            if current.status == "editing":
                raise HoldingImportConflict("editing", "holding import edit is already in progress")
            if current.status == "ready" and _aware(current.expires_at) < claim_now:
                current.status = "expired"
                db.flush()
                self._commit(db)
                self._finalize_terminal_storage(db, current)
                raise HoldingImportConflict("expired", "holding import session expired")
            raise HoldingImportConflict()
        session = db.scalar(select(HoldingImportSession).where(HoldingImportSession.session_id == token))
        if session is None:
            raise HoldingImportNotFound()
        candidate = db.scalar(
            select(HoldingImportCandidate).where(
                HoldingImportCandidate.id == candidate_id,
                HoldingImportCandidate.session_id == session.id,
            )
        )
        if candidate is None:
            raise HoldingImportNotFound()
        payload = changes.model_dump(exclude_unset=True) if hasattr(changes, "model_dump") else dict(changes)
        action = payload.pop("action", None)
        if action not in {None, "reject"}:
            raise HoldingImportConflict("invalid_action", "holding import action rejected")
        selected = payload.pop("selected_code", None)
        if action == "reject":
            candidate.status = OCRCandidateStatus.REJECTED.value
            candidate.action = OCRCandidateAction.REJECT.value
            candidate.selected_code = None
            candidate.selected_at = None
            session.status = "ready"
            db.flush()
            return candidate
        if candidate.status == OCRCandidateStatus.REJECTED.value:
            candidate.status = OCRCandidateStatus.PENDING.value
            candidate.action = OCRCandidateAction.NONE.value
        for key in ("name", "shares", "cost_price", "target_weight", "user_note"):
            if key in payload:
                value = payload[key]
                if key in {"shares", "cost_price", "target_weight"} and value is not None:
                    try:
                        value = Decimal(str(value))
                    except (InvalidOperation, ValueError):
                        raise HoldingImportConflict("invalid_numeric", "numeric holding field rejected") from None
                    maximum = Decimal("1") if key == "target_weight" else Decimal("1000000000")
                    scale = 6 if key == "target_weight" else (4 if key == "shares" else 6)
                    if not value.is_finite() or value < 0 or value > maximum or value.quantize(Decimal(1).scaleb(-scale)) != value:
                        raise HoldingImportConflict("invalid_numeric", "numeric holding field rejected")
                    if key == "target_weight":
                        value = float(value)
                elif key in {"name", "user_note"} and value is not None:
                    if not isinstance(value, str) or len(value) > 2000:
                        raise HoldingImportConflict("invalid_text", "holding text field rejected")
                    try:
                        value = validate_safe_text(value)
                    except ValueError:
                        raise HoldingImportConflict("invalid_text", "holding text field rejected") from None
                setattr(candidate, key, value)
        if "ts_code" in payload and payload["ts_code"] is not None:
            selected = payload["ts_code"]
        if selected is not None:
            if not isinstance(selected, str) or re.fullmatch(r"[0-9]{6}\.(SH|SZ|BJ)", selected.strip().upper()) is None:
                raise HoldingImportConflict("invalid_code", "selected holding code rejected")
            selected = selected.strip().upper()
            if db.scalar(select(Instrument).where(Instrument.ts_code == selected)) is None:
                raise HoldingImportConflict("unknown_code", "selected holding code not configured")
            candidate.ts_code = selected
            candidate.selected_code = selected
            candidate.selected_at = _aware(self.clock())
            candidate.match_status = OCRMatchStatus.MATCHED.value
            candidate.status = OCRCandidateStatus.REVIEWED.value
            candidate.action = OCRCandidateAction.NONE.value
        session.status = "ready"
        db.flush()
        return candidate

    def confirm(self, db: Session, session_id: str) -> dict[str, Any]:
        work_db = self._owned_db(db)
        try:
            return self._confirm_owned(work_db, session_id)
        finally:
            work_db.close()

    def _confirm_owned(self, db: Session, session_id: str) -> dict[str, Any]:
        with self._confirm_lock(session_id):
            self.cleanup_expired(db)
            token = _safe_token(session_id)
            session = db.scalar(select(HoldingImportSession).where(HoldingImportSession.session_id == token))
            if session is None:
                raise HoldingImportNotFound()
            if session.status == "confirmed":
                self._finalize_terminal_storage(db, session)
                return {"status": "confirmed", "session_id": session.session_id, "upserted": sum(c.status == "confirmed" for c in session.candidates)}
            if session.status == "confirming":
                raise HoldingImportConflict("confirming", "holding import confirmation is already in progress")
            if session.status in {"cancelled", "expired", "failed"}:
                raise HoldingImportConflict()
            now = _aware(self.clock())
            if _aware(session.expires_at) < now:
                session.status = "expired"
                db.flush()
                self._commit(db)
                self._finalize_terminal_storage(db, session)
                raise HoldingImportConflict("expired", "holding import session expired")
            active = [item for item in session.candidates if item.status != OCRCandidateStatus.REJECTED.value]
            active.sort(key=lambda item: (item.selected_code or "", item.row_index))
            selected_codes: set[str] = set()
            for candidate in active:
                if candidate.status != OCRCandidateStatus.REVIEWED.value or candidate.action != OCRCandidateAction.NONE.value:
                    raise HoldingImportConflict("unresolved", "all holding rows require explicit review")
                if not candidate.selected_code or candidate.shares is None or candidate.cost_price is None:
                    raise HoldingImportConflict("unresolved", "all selected rows require code, shares, and cost")
                if candidate.selected_code in selected_codes:
                    raise HoldingImportConflict("duplicate", "duplicate selected holding code")
                selected_codes.add(candidate.selected_code)
                if db.scalar(select(Instrument).where(Instrument.ts_code == candidate.selected_code)) is None:
                    raise HoldingImportConflict("unknown_code", "selected holding code not configured")
            try:
                # The CAS is the cross-process authority.
                if self.before_claim is not None:
                    self.before_claim()
                claim_now = _aware(self.clock())
                changed = db.execute(
                    update(HoldingImportSession)
                    .execution_options(synchronize_session=False)
                    .where(
                        HoldingImportSession.session_id == token,
                        HoldingImportSession.status == "ready",
                        HoldingImportSession.expires_at >= claim_now,
                    )
                    .values(status="confirming")
                ).rowcount
                if changed != 1:
                    db.rollback()
                    winner = db.scalar(select(HoldingImportSession).where(HoldingImportSession.session_id == token))
                    if winner is not None and winner.status == "confirmed":
                        self._finalize_terminal_storage(db, winner)
                        return {"status": "confirmed", "session_id": winner.session_id, "upserted": sum(c.status == "confirmed" for c in winner.candidates)}
                    if winner is not None and winner.status == "confirming":
                        raise HoldingImportConflict("confirming", "holding import confirmation is already in progress")
                    if winner is not None and winner.status == "ready" and _aware(winner.expires_at) < claim_now:
                        winner.status = "expired"
                        db.flush()
                        self._commit(db)
                        self._finalize_terminal_storage(db, winner)
                        raise HoldingImportConflict("expired", "holding import session expired")
                    raise HoldingImportConflict()
                db.refresh(session)
                before = {item.id for item in db.scalars(select(Holding)).all()}
                for candidate in active:
                    self.holding_service.upsert(
                        db,
                        ts_code=candidate.selected_code,
                        shares=candidate.shares,
                        cost_price=candidate.cost_price,
                        target_weight=candidate.target_weight,
                        notes=candidate.user_note,
                    )
                after = {item.id for item in db.scalars(select(Holding)).all()}
                if not before.issubset(after):
                    raise HoldingImportConflict("atomicity", "holding import changed an unrelated holding")
                for candidate in active:
                    candidate.status = OCRCandidateStatus.CONFIRMED.value
                    candidate.action = OCRCandidateAction.CONFIRM.value
                session.status = "confirmed"
                session.confirmed_at = claim_now
                db.flush()
                self._commit(db)
            except Exception:
                db.rollback()
                raise
            self._finalize_terminal_storage(db, session)
            return {"status": "confirmed", "session_id": session.session_id, "upserted": len(active)}

    def cancel(self, db: Session, session_id: str) -> dict[str, Any]:
        work_db = self._owned_db(db)
        try:
            return self._cancel_owned(work_db, session_id)
        finally:
            work_db.close()

    def _cancel_owned(self, db: Session, session_id: str) -> dict[str, Any]:
        self.cleanup_expired(db)
        token = _safe_token(session_id)
        claim_now = _aware(self.clock())
        changed = db.execute(
            update(HoldingImportSession)
            .execution_options(synchronize_session=False)
            .where(
                HoldingImportSession.session_id == token,
                HoldingImportSession.status.in_(["ready", "editing"]),
                HoldingImportSession.expires_at >= claim_now,
            )
            .values(status="cancelled", cancelled_at=claim_now)
        ).rowcount
        session = db.scalar(select(HoldingImportSession).where(HoldingImportSession.session_id == token))
        if session is None:
            raise HoldingImportNotFound()
        if changed != 1:
            if session.status == "confirmed":
                raise HoldingImportConflict("confirmed", "confirmed holding import cannot be cancelled")
            if session.status == "confirming":
                raise HoldingImportConflict("confirming", "holding import confirmation is already in progress")
            if session.status == "cancelled":
                self._finalize_terminal_storage(db, session)
                return {"status": "cancelled", "session_id": session.session_id}
            if session.status == "expired":
                self._finalize_terminal_storage(db, session)
                return {"status": "expired", "session_id": session.session_id}
            if session.status in {"ready", "editing"} and _aware(session.expires_at) < claim_now:
                session.status = "expired"
                db.flush()
                self._commit(db)
                self._finalize_terminal_storage(db, session)
                return {"status": "expired", "session_id": session.session_id}
            raise HoldingImportConflict()
        db.refresh(session)
        self._commit(db)
        self._finalize_terminal_storage(db, session)
        return {"status": "cancelled", "session_id": session.session_id}

    def set_cloud_consent(self, db: Session, session_id: str, consent: bool) -> HoldingImportSession:
        work_db = self._owned_db(db)
        try:
            self._set_cloud_consent_owned(work_db, session_id, consent)
            self._commit(work_db)
        finally:
            work_db.close()
        return self._read_detached(db, session_id)

    def _set_cloud_consent_owned(self, db: Session, session_id: str, consent: bool) -> HoldingImportSession:
        token = _safe_token(session_id)
        session = db.scalar(select(HoldingImportSession).where(HoldingImportSession.session_id == token))
        if session is None:
            raise HoldingImportNotFound()
        if not self.settings.ocr_cloud_review_enabled:
            raise HoldingImportConflict("cloud_disabled", "cloud review is disabled")
        if session.status in {"confirmed", "cancelled", "expired"}:
            raise HoldingImportConflict()
        session.cloud_consent = bool(consent)
        session.cloud_consent_at = _aware(self.clock()) if consent else None
        db.flush()
        return session

    # Descriptive aliases keep the service convenient for task code and tests
    # without introducing a second implementation path.
    create_session = import_bytes
    get_session = get
    update_candidate = edit_candidate
    confirm_session = confirm
    cancel_session = cancel
    cleanup_expired_sessions = cleanup_expired
