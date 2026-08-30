from __future__ import annotations

import hashlib
import io
import json
import multiprocessing
import os
import threading
import time
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from app.core.config import Settings
from app.models import Holding, HoldingImportCandidate, HoldingImportSession
from app.models.entities import _SafeImportText
from app.ocr.contracts import ConfidenceEntry, HoldingCandidate, OCRBox, OCRLine, OCRResult, OCRUnavailable
from app.ocr.fake import FakeOCRBackend
from app.ocr.image_validation import ImageValidationError, ValidatedImage, validate_image_bytes
from app.ocr.paddle_adapter import PaddleOCRAdapter
from app.services.holding_service import HoldingService
from PIL import Image
from pydantic import ValidationError
from sqlalchemy import inspect, text
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.exc import IntegrityError
from sqlalchemy.schema import CreateTable


def _image_bytes(fmt: str, size: tuple[int, int] = (4, 3)) -> bytes:
    output = io.BytesIO()
    Image.new("RGB", size, color=(25, 80, 120)).save(output, format=fmt)
    return output.getvalue()


def _sleeping_worker(conn, *args) -> None:
    del args
    time.sleep(2)
    conn.send({"status": "completed", "lines": []})
    conn.close()


def _response_then_sleep_worker(conn, *args) -> None:
    del args
    conn.send({"status": "completed", "lines": []})
    time.sleep(2)


@pytest.mark.parametrize("fmt,mime", [("PNG", "image/png"), ("JPEG", "image/jpeg"), ("WEBP", "image/webp")])
def test_image_validation_returns_only_safe_metadata(fmt: str, mime: str) -> None:
    metadata = validate_image_bytes(_image_bytes(fmt), declared_mime=mime)
    assert metadata.mime_type == mime
    assert (metadata.width, metadata.height) == (4, 3)
    assert len(metadata.sha256) == 64
    assert not hasattr(metadata, "pixels")


def test_image_validation_rejects_mismatch_corruption_and_bytes_plus_one() -> None:
    with pytest.raises(ImageValidationError, match="mime"):
        validate_image_bytes(_image_bytes("PNG"), declared_mime="image/jpeg")
    with pytest.raises(ImageValidationError):
        validate_image_bytes(_image_bytes("PNG")[:20], declared_mime="image/png")
    with pytest.raises(ImageValidationError, match="large"):
        validate_image_bytes(_image_bytes("PNG"), declared_mime="image/png", max_bytes=10)
    jpeg = _image_bytes("JPEG")
    with pytest.raises(ImageValidationError, match="trailing"):
        validate_image_bytes(jpeg + b"evil", declared_mime="image/jpeg")
    with pytest.raises(ImageValidationError, match="trailing"):
        validate_image_bytes(jpeg + b"evil\xff\xd9", declared_mime="image/jpeg")


def test_image_validation_rejects_dimensions_and_trailing_polyglot() -> None:
    with pytest.raises(ImageValidationError, match="dimension"):
        validate_image_bytes(_image_bytes("PNG", (20, 3)), declared_mime="image/png", max_width=10)
    with pytest.raises(ImageValidationError, match="pixel"):
        validate_image_bytes(_image_bytes("PNG", (20, 20)), declared_mime="image/png", max_pixels=100)
    with pytest.raises(ImageValidationError, match="trailing"):
        validate_image_bytes(_image_bytes("PNG") + b"not-a-second-format", declared_mime="image/png")


def test_image_validation_translates_decoder_bomb_without_mutating_pillow_global() -> None:
    previous = Image.MAX_IMAGE_PIXELS
    with pytest.raises(ImageValidationError, match="pixel"):
        validate_image_bytes(_image_bytes("PNG", (20, 20)), declared_mime="image/png", max_pixels=100)
    assert Image.MAX_IMAGE_PIXELS == previous


def test_ocr_contracts_are_immutable_bounded_and_extra_forbid() -> None:
    box = OCRBox(points=((0.0, 0.0), (4.0, 0.0), (4.0, 3.0), (0.0, 3.0)))
    line = OCRLine(text="512480.SH 半导体ETF", confidence=0.98, box=box)
    result = OCRResult(
        lines=(line,),
        backend="fake",
        model="fixture",
        version="1",
        processed_at=datetime.now(UTC),
    )
    assert result.lines[0].text.startswith("512480")
    with pytest.raises(ValidationError):
        OCRLine(text="x", confidence=1.1, box=box)
    with pytest.raises(ValidationError):
        OCRLine(text="x", confidence=0.2, box=box, account_number="nope")
    with pytest.raises(ValidationError):
        OCRLine(text="x", confidence=0.2, box=OCRBox(points=((0, 0), (1, 1))))
    with pytest.raises((ValidationError, TypeError)):
        result.lines = ()
    candidate = HoldingCandidate(
        row_index=0,
        field_confidence=(ConfidenceEntry(field="ts_code", confidence=0.9),),
    )
    with pytest.raises((ValidationError, TypeError, AttributeError)):
        candidate.field_confidence[0].confidence = 0.1
    with pytest.raises(ValidationError):
        HoldingCandidate(row_index=0, field_confidence=(ConfidenceEntry(field="password", confidence=0.9),))
    with pytest.raises(ValidationError):
        OCRUnavailable(reason="arbitrary_exception_text")
    with pytest.raises(ValidationError):
        ConfidenceEntry(field="user_note", confidence=0.9)


def test_fake_backend_is_deterministic_and_never_exposes_sensitive_fields() -> None:
    backend = FakeOCRBackend(
        lines=(OCRLine(text="512480.SH 100 1.234", confidence=0.9, box=None),),
    )
    first = backend.recognize(b"fixture")
    second = backend.recognize(b"fixture")
    assert first == second
    assert first.lines[0].text == "512480.SH 100 1.234"
    assert {"account", "password", "identity", "account_number"}.isdisjoint(first.model_dump())


def test_paddle_adapter_is_lazy_and_sanitizes_unavailable(tmp_path: Path) -> None:
    unavailable = PaddleOCRAdapter(model_dir=tmp_path / "missing", model="bad model / secret", version="raw text").recognize(b"not-an-image")
    assert unavailable.status == "ocr_unavailable"
    assert "Traceback" not in unavailable.reason
    assert "download" not in unavailable.reason.lower()
    assert unavailable.model == "unavailable"
    assert unavailable.version == "unavailable"


def test_paddle_requires_strict_local_manifest_and_nonempty_det_rec_artifacts(tmp_path: Path) -> None:
    (tmp_path / "arbitrary.json").write_text("{}", encoding="utf-8")
    image = _image_bytes("PNG")
    assert PaddleOCRAdapter(model_dir=tmp_path).recognize(image).reason == "model_directory_unqualified"
    (tmp_path / "arbitrary.json").unlink()
    manifest_files = {}
    for component in ("det", "rec"):
        (tmp_path / component).mkdir()
        manifest_files[component] = []
        for suffix in (".pdmodel", ".pdiparams"):
            path = tmp_path / component / f"inference{suffix}"
            path.write_bytes(component.encode())
            manifest_files[component].append({"path": f"{component}/{path.name}", "size": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    (tmp_path / "manifest.json").write_text(
        json.dumps({"version": "paddle-local-v1", "det": {"files": manifest_files["det"]}, "rec": {"files": manifest_files["rec"]}}),
        encoding="utf-8",
    )
    assert PaddleOCRAdapter(model_dir=tmp_path).recognize(image).reason in {
        "paddleocr_package_missing",
        "paddle_package_missing",
        "engine_unavailable",
    }


def test_paddle_hard_timeout_terminates_spawned_worker(tmp_path: Path) -> None:
    image = _image_bytes("PNG")
    files = {}
    for component in ("det", "rec"):
        directory = tmp_path / component
        directory.mkdir()
        for suffix in (".pdmodel", ".pdiparams"):
            path = directory / f"inference{suffix}"
            path.write_bytes(component.encode() + suffix.encode())
            files.setdefault(component, []).append({"path": f"{component}/{path.name}", "size": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    (tmp_path / "manifest.json").write_text(json.dumps({"version": "paddle-local-v1", "det": {"files": files["det"]}, "rec": {"files": files["rec"]}}), encoding="utf-8")
    start = time.monotonic()
    result = PaddleOCRAdapter(model_dir=tmp_path, timeout_seconds=0.05, worker_target=_sleeping_worker).recognize(image)
    assert time.monotonic() - start < 1.0
    assert result.status == "ocr_unavailable"
    assert result.reason == "timeout"


def test_paddle_start_failure_closes_both_pipes_without_process_cleanup(monkeypatch) -> None:
    class FakeConn:
        def __init__(self):
            self.closed = False

        def close(self):
            self.closed = True

        def poll(self, timeout):
            del timeout
            return False

    class FakeProcess:
        def start(self):
            raise AssertionError("synthetic start failure")

        def is_alive(self):
            raise AssertionError("must not inspect an unstarted process")

    class FakeContext:
        def __init__(self):
            self.parent = FakeConn()
            self.child = FakeConn()

        def Pipe(self, duplex=False):
            assert duplex is False
            return self.parent, self.child

        def Process(self, **kwargs):
            del kwargs
            return FakeProcess()

    context = FakeContext()
    monkeypatch.setattr("multiprocessing.get_context", lambda name: context)
    adapter = PaddleOCRAdapter(model_dir=Path("."), worker_target=_sleeping_worker)
    result = adapter._run_worker(b"payload")
    assert result["reason"] == "engine_unavailable"
    assert context.parent.closed and context.child.closed


def test_paddle_response_then_sleep_worker_is_cleaned_up() -> None:
    adapter = PaddleOCRAdapter(model_dir=Path("."), timeout_seconds=2.0, worker_target=_response_then_sleep_worker)
    before = {child.pid for child in multiprocessing.active_children()}
    result = adapter._run_worker(b"payload")
    after = {child.pid for child in multiprocessing.active_children()}
    assert result["status"] == "completed"
    assert after == before


def test_paddle_rejects_root_extra_entries(tmp_path: Path) -> None:
    image = _image_bytes("PNG")
    for component in ("det", "rec"):
        directory = tmp_path / component
        directory.mkdir()
        for suffix in (".pdmodel", ".pdiparams"):
            (directory / f"inference{suffix}").write_bytes(component.encode())
    manifest = {
        "version": "paddle-local-v1",
        "det": {"files": [{"path": f"det/inference{suffix}", "size": len(b"det"), "sha256": hashlib.sha256(b"det").hexdigest()} for suffix in (".pdmodel", ".pdiparams")]},
        "rec": {"files": [{"path": f"rec/inference{suffix}", "size": len(b"rec"), "sha256": hashlib.sha256(b"rec").hexdigest()} for suffix in (".pdmodel", ".pdiparams")]},
    }
    (tmp_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (tmp_path / "extra.bin").write_bytes(b"x")
    assert PaddleOCRAdapter(model_dir=tmp_path).recognize(image).reason == "model_directory_unqualified"
    (tmp_path / "extra.bin").unlink()
    (tmp_path / "extra").mkdir()
    assert PaddleOCRAdapter(model_dir=tmp_path).recognize(image).reason == "model_directory_unqualified"
    (tmp_path / "extra").rmdir()
    try:
        (tmp_path / "extra-link").symlink_to(tmp_path / "det", target_is_directory=True)
    except OSError:
        pytest.skip("symlink creation unavailable on this host")
    assert PaddleOCRAdapter(model_dir=tmp_path).recognize(image).reason == "model_directory_unqualified"


def test_paddle_revalidates_forged_validated_image(tmp_path: Path) -> None:
    image = _image_bytes("PNG")
    metadata = validate_image_bytes(image, declared_mime="image/png")
    forged = ValidatedImage(payload=image, metadata=metadata)
    object.__setattr__(forged, "payload", image + b"evil")
    result = PaddleOCRAdapter(model_dir=tmp_path).recognize(forged)
    assert result.status == "ocr_unavailable"


def test_ocr_settings_default_cloud_off_and_bounds(tmp_path: Path) -> None:
    settings = Settings(_env_file=None)
    assert settings.ocr_mode == "local_paddle"
    assert settings.ocr_cloud_review_enabled is False
    assert settings.ocr_transient_ttl_minutes == 15
    assert settings.ocr_transient_root.resolve() != settings.reports_dir.resolve()
    with pytest.raises(ValidationError):
        Settings(_env_file=None, OCR_TRANSIENT_TTL_MINUTES=0)
    with pytest.raises(ValidationError):
        Settings(_env_file=None, OCR_MAX_BYTES=0)
    with pytest.raises(ValidationError):
        Settings(_env_file=None, OCR_MODE="cloud_review")
    cloud = Settings(_env_file=None, OCR_MODE="local_paddle", OCR_CLOUD_REVIEW_ENABLED=True)
    assert cloud.ocr_cloud_review_enabled is True
    disabled = Settings(_env_file=None, APP_ENV="production", AUTH_ENABLED=False, OCR_MODE="disabled")
    assert disabled.ocr_mode == "disabled"
    for blocked in (settings.reports_dir, Path(__file__).parents[1] / "app" / "static", settings.ocr_local_model_dir):
        with pytest.raises(ValidationError):
            Settings(_env_file=None, OCR_TRANSIENT_ROOT=blocked)


@pytest.mark.skipif(os.name == "nt", reason="Windows symlink creation requires elevated privileges")
def test_ocr_settings_rejects_transient_symlink_and_insecure_production_root(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    link = tmp_path / "link"
    link.symlink_to(target, target_is_directory=True)
    with pytest.raises(ValidationError):
        Settings(_env_file=None, OCR_TRANSIENT_ROOT=link)
    os.chmod(target, 0o755)
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            APP_ENV="production",
            AUTH_ENABLED=False,
            OCR_TRANSIENT_ROOT=target,
            OCR_LOCAL_MODEL_DIR=target,
        )


def test_import_models_allow_only_sanitized_candidate_fields(db_session) -> None:
    session = HoldingImportSession(
        session_id="a" * 16,
        status="ready",
        image_sha256="a" * 64,
        detected_mime="image/png",
        image_bytes=123,
        image_width=4,
        image_height=3,
        ocr_mode="local_paddle",
        ocr_backend="fake",
        ocr_model="fixture",
        ocr_version="1",
        candidate_count=1,
        expires_at=datetime.now(UTC),
        storage_key="c" * 32,
    )
    db_session.add(session)
    db_session.flush()
    candidate = HoldingImportCandidate(
        session_id=session.id,
        row_index=0,
        ts_code="512480.SH",
        name="半导体ETF",
        shares=100,
        cost_price=1.234,
        target_weight=0.2,
        user_note="review",
        match_status="matched",
        status="pending",
        action="none",
        safe_alternatives_json=[],
        field_confidence_json=({"field": "ts_code", "confidence": 0.99},),
        normalized_ocr_text_hash="b" * 64,
    )
    db_session.add(candidate)
    db_session.flush()
    columns = {column.name for column in inspect(HoldingImportSession).columns}
    columns |= {column.name for column in inspect(HoldingImportCandidate).columns}
    forbidden = {"image_bytes_payload", "pixels", "raw_ocr", "raw_text", "account_number", "password"}
    assert columns.isdisjoint(forbidden)
    assert "image_bytes" in columns  # metadata byte count, not image payload
    with pytest.raises(IntegrityError):
        db_session.execute(
            text("UPDATE holding_import_candidates SET action='confirm', status='pending' WHERE id=:id"),
            {"id": candidate.id},
        )
        db_session.flush()
    db_session.rollback()


def test_import_json_serialization_rejects_sensitive_keys_before_flush(db_session) -> None:
    with pytest.raises(ValueError):
        HoldingImportCandidate(
            session_id=1,
            row_index=0,
            match_status="matched",
            status="pending",
            action="none",
            safe_alternatives_json=["512480.SH"],
            field_confidence_json={"password": 1.0},
            normalized_ocr_text_hash="b" * 64,
        )


def test_import_sqlite_constraint_rejects_sensitive_raw_json(db_session) -> None:
    session = HoldingImportSession(
        session_id="b" * 16,
        status="ready",
        image_sha256="a" * 64,
        detected_mime="image/png",
        image_bytes=1,
        image_width=1,
        image_height=1,
        ocr_mode="local_paddle",
        ocr_backend="fake",
        ocr_model="fixture",
        ocr_version="1",
        candidate_count=1,
        expires_at=datetime.now(UTC),
    )
    db_session.add(session)
    db_session.flush()
    with pytest.raises(IntegrityError):
        db_session.execute(
            text("INSERT INTO holding_import_candidates (session_id,row_index,match_status,status,action,safe_alternatives_json,field_confidence_json,normalized_ocr_text_hash) VALUES (:sid,0,'matched','pending','none','[\\\"account\\\"]','[]',:hash)"),
            {"sid": session.id, "hash": "b" * 64},
        )
        db_session.flush()
    db_session.rollback()


def test_import_sqlite_cloud_consent_is_exactly_bidirectional(db_session) -> None:
    base = {
        "image_sha256": "a" * 64,
        "detected_mime": "image/png",
        "image_bytes": 1,
        "image_width": 1,
        "image_height": 1,
        "ocr_mode": "local_paddle",
        "ocr_backend": "fake",
        "ocr_model": "fixture",
        "ocr_version": "1",
        "candidate_count": 0,
        "expires_at": datetime.now(UTC),
    }
    timestamp = datetime.now(UTC)
    for index, consent, consent_at, valid in (
        (10, 0, None, True),
        (11, 1, timestamp, True),
        (12, 0, timestamp, False),
        (13, 1, None, False),
    ):
        statement = text("INSERT INTO holding_import_sessions (session_id,status,image_sha256,detected_mime,image_bytes,image_width,image_height,ocr_mode,ocr_backend,ocr_model,ocr_version,candidate_count,cloud_consent,cloud_consent_at,expires_at) VALUES (:session_id,'ready',:image_sha256,:detected_mime,:image_bytes,:image_width,:image_height,:ocr_mode,:ocr_backend,:ocr_model,:ocr_version,:candidate_count,:cloud_consent,:cloud_consent_at,:expires_at)")
        if valid:
            db_session.execute(statement, {**base, "session_id": f"{index:02x}" + "e" * 14, "cloud_consent": consent, "cloud_consent_at": consent_at})
            db_session.flush()
            db_session.rollback()
        else:
            with pytest.raises(IntegrityError):
                db_session.execute(statement, {**base, "session_id": f"{index:02x}" + "e" * 14, "cloud_consent": consent, "cloud_consent_at": consent_at})
                db_session.flush()
            db_session.rollback()


def test_import_type_decorator_rejects_noncanonical_persisted_json(db_session) -> None:
    session = HoldingImportSession(
        session_id="c" * 16,
        status="ready",
        image_sha256="a" * 64,
        detected_mime="image/png",
        image_bytes=1,
        image_width=1,
        image_height=1,
        ocr_mode="local_paddle",
        ocr_backend="fake",
        ocr_model="fixture",
        ocr_version="1",
        candidate_count=1,
        expires_at=datetime.now(UTC),
    )
    db_session.add(session)
    db_session.flush()
    candidate = HoldingImportCandidate(
        session_id=session.id,
        row_index=0,
        match_status="matched",
        status="pending",
        action="none",
        safe_alternatives_json=("512480.SH",),
        field_confidence_json=(),
        normalized_ocr_text_hash="b" * 64,
    )
    db_session.add(candidate)
    db_session.flush()
    db_session.execute(
        text('UPDATE holding_import_candidates SET safe_alternatives_json=\'[ "512480.SH" ]\' WHERE id=:id'),
        {"id": candidate.id},
    )
    db_session.expire(candidate)
    with pytest.raises(ValueError, match="canonical"):
        _ = candidate.safe_alternatives_json
    db_session.rollback()


@pytest.mark.parametrize("marker", ["Bearer abc", "token abc", "passwd=abc", "\\\\server\\share", "name\nline", "name\rline", "name\tline"])
def test_import_safe_text_type_rejects_raw_sql_markers_on_orm_read(db_session, marker: str) -> None:
    session = HoldingImportSession(
        session_id="e" * 16,
        status="ready",
        image_sha256="a" * 64,
        detected_mime="image/png",
        image_bytes=1,
        image_width=1,
        image_height=1,
        ocr_mode="local_paddle",
        ocr_backend="fake",
        ocr_model="fixture",
        ocr_version="1",
        candidate_count=1,
        expires_at=datetime.now(UTC),
    )
    db_session.add(session)
    db_session.flush()
    candidate = HoldingImportCandidate(
        session_id=session.id,
        row_index=0,
        ts_code="512480.SH",
        name="合法名称",
        match_status="matched",
        status="pending",
        action="none",
        safe_alternatives_json=(),
        field_confidence_json=(),
        normalized_ocr_text_hash="b" * 64,
    )
    db_session.add(candidate)
    db_session.flush()
    with pytest.raises(IntegrityError):
        db_session.execute(text("UPDATE holding_import_candidates SET user_note=:marker WHERE id=:id"), {"id": candidate.id, "marker": marker})
        db_session.flush()
    db_session.rollback()


def test_import_sqlite_nul_triggers_reject_insert_and_update(db_session) -> None:
    trigger_names = set(db_session.scalars(text("SELECT name FROM sqlite_master WHERE type='trigger' AND name LIKE 'trg_holding_import_candidates_no_nul_%'")))
    assert trigger_names == {
        "trg_holding_import_candidates_no_nul_insert",
        "trg_holding_import_candidates_no_nul_update",
    }
    values = {
        "session_id": "a" * 16,
        "image_sha256": "a" * 64,
        "detected_mime": "image/png",
        "image_bytes": 1,
        "image_width": 1,
        "image_height": 1,
        "ocr_mode": "local_paddle",
        "ocr_backend": "fake",
        "ocr_model": "fixture",
        "ocr_version": "1",
        "candidate_count": 1,
        "expires_at": datetime.now(UTC),
    }
    db_session.execute(text("INSERT INTO holding_import_sessions (session_id,status,image_sha256,detected_mime,image_bytes,image_width,image_height,ocr_mode,ocr_backend,ocr_model,ocr_version,candidate_count,cloud_consent,expires_at) VALUES (:session_id,'ready',:image_sha256,:detected_mime,:image_bytes,:image_width,:image_height,:ocr_mode,:ocr_backend,:ocr_model,:ocr_version,:candidate_count,0,:expires_at)"), values)
    db_session.flush()
    session_pk = db_session.scalar(text("SELECT id FROM holding_import_sessions WHERE session_id=:session_id"), values)
    with pytest.raises(IntegrityError):
        db_session.execute(text("INSERT INTO holding_import_candidates (session_id,row_index,match_status,status,action,safe_alternatives_json,field_confidence_json,normalized_ocr_text_hash,name) VALUES (:sid,0,'matched','pending','none','[]','[]',:hash,:name)"), {"sid": session_pk, "hash": "b" * 64, "name": "坏\x00名"})
        db_session.flush()
    db_session.execute(text("INSERT INTO holding_import_candidates (session_id,row_index,match_status,status,action,safe_alternatives_json,field_confidence_json,normalized_ocr_text_hash,name) VALUES (:sid,1,'matched','pending','none','[]','[]',:hash,:name)"), {"sid": session_pk, "hash": "c" * 64, "name": "合法"})
    db_session.flush()
    with pytest.raises(IntegrityError):
        db_session.execute(text("UPDATE holding_import_candidates SET user_note=:value WHERE row_index=1"), {"value": "坏\x00备注"})
        db_session.flush()
    db_session.rollback()


@pytest.mark.parametrize("control", ["\n", "\r", "\t", "\x00"])
def test_import_safe_text_rejects_unicode_control_characters(control: str) -> None:
    converter = _SafeImportText(128)
    with pytest.raises(ValueError, match="control"):
        converter.process_bind_param(f"名称{control}", None)
    with pytest.raises(ValueError, match="control"):
        converter.process_result_value(f"名称{control}", None)


def test_import_selected_code_timestamp_and_action_combinations_are_coherent(db_session) -> None:
    session = HoldingImportSession(
        session_id="f" * 16,
        status="ready",
        image_sha256="a" * 64,
        detected_mime="image/png",
        image_bytes=1,
        image_width=1,
        image_height=1,
        ocr_mode="local_paddle",
        ocr_backend="fake",
        ocr_model="fixture",
        ocr_version="1",
        candidate_count=8,
        expires_at=datetime.now(UTC),
    )
    db_session.add(session)
    db_session.commit()
    statement = text("INSERT INTO holding_import_candidates (session_id,row_index,match_status,status,action,safe_alternatives_json,field_confidence_json,normalized_ocr_text_hash,selected_code,selected_at) VALUES (:sid,:row,'matched',:status,:action,'[]','[]',:hash,:code,:selected_at)")
    valid = (
        (0, "pending", "none", None, None),
        (1, "reviewed", "none", "512480.SH", datetime.now(UTC)),
        (2, "rejected", "reject", None, None),
        (3, "confirmed", "confirm", "512480.SH", datetime.now(UTC)),
    )
    for row, status, action, code, selected_at in valid:
        db_session.execute(statement, {"sid": session.id, "row": row, "status": status, "action": action, "hash": f"{row + 1:064x}", "code": code, "selected_at": selected_at})
        db_session.flush()
        db_session.rollback()
    invalid = (
        (4, "pending", "none", "512480.SH", None),
        (5, "pending", "none", None, datetime.now(UTC)),
        (6, "rejected", "reject", "512480.SH", datetime.now(UTC)),
        (7, "confirmed", "confirm", None, None),
    )
    for row, status, action, code, selected_at in invalid:
        with pytest.raises(IntegrityError):
            db_session.execute(statement, {"sid": session.id, "row": row, "status": status, "action": action, "hash": f"{row + 1:064x}", "code": code, "selected_at": selected_at})
            db_session.flush()
        db_session.rollback()


def test_import_session_terminal_timestamps_are_bidirectionally_coherent(db_session) -> None:
    values = {
        "session_id": "d" * 16,
        "image_sha256": "a" * 64,
        "detected_mime": "image/png",
        "image_bytes": 1,
        "image_width": 1,
        "image_height": 1,
        "ocr_mode": "local_paddle",
        "ocr_backend": "fake",
        "ocr_model": "fixture",
        "ocr_version": "1",
        "candidate_count": 0,
        "expires_at": datetime.now(UTC),
    }
    with pytest.raises(IntegrityError):
        db_session.execute(text("INSERT INTO holding_import_sessions (session_id,status,image_sha256,detected_mime,image_bytes,image_width,image_height,ocr_mode,ocr_backend,ocr_model,ocr_version,candidate_count,cloud_consent,expires_at,confirmed_at) VALUES (:session_id,'ready',:image_sha256,:detected_mime,:image_bytes,:image_width,:image_height,:ocr_mode,:ocr_backend,:ocr_model,:ocr_version,:candidate_count,0,:expires_at,:confirmed_at)"), {**values, "confirmed_at": datetime.now(UTC)})
        db_session.flush()
    db_session.rollback()


def test_import_tables_compile_for_postgresql_and_indexes_have_no_duplicate_expiry() -> None:
    session_sql = str(CreateTable(HoldingImportSession.__table__).compile(dialect=postgresql.dialect()))
    candidate_sql = str(CreateTable(HoldingImportCandidate.__table__).compile(dialect=postgresql.dialect()))
    sqlite_candidate_sql = str(CreateTable(HoldingImportCandidate.__table__).compile(dialect=sqlite.dialect()))
    assert "cloud_consent = 1" not in session_sql
    assert "length(safe_alternatives_json)" not in candidate_sql
    assert "position(chr(92) in name) = 0" in candidate_sql
    assert "instr(name, char(92)) = 0" in sqlite_candidate_sql
    session_indexes = {index.name for index in HoldingImportSession.__table__.indexes}
    candidate_indexes = {index.name for index in HoldingImportCandidate.__table__.indexes}
    assert "ix_holding_import_sessions_expires_at" in session_indexes
    assert "ix_holding_import_sessions_image_sha256" in session_indexes
    assert "ix_holding_import_candidates_normalized_ocr_text_hash" in candidate_indexes


def test_migration_declares_expected_revision() -> None:
    migration = Path(__file__).parents[1] / "alembic" / "versions" / "b3c4d5e6f7a8_holding_import.py"
    source = migration.read_text(encoding="utf-8")
    assert "revision: str = \"b3c4d5e6f7a8\"" in source
    assert "down_revision: str | None = \"a2b3c4d5e6f7\"" in source


def test_holding_import_service_requires_explicit_review_before_writing(db_session, tmp_path: Path) -> None:
    from app.models import Instrument
    from app.services.holding_import_service import HoldingImportService

    db_session.add(Instrument(ts_code="999006.SH", symbol="999006", name="测试半导体ETF", exchange="SH"))
    db_session.flush()
    db_session.commit()
    service = HoldingImportService(
        Settings(_env_file=None, OCR_TRANSIENT_ROOT=tmp_path),
        ocr_backend=FakeOCRBackend(
            lines=(OCRLine(text="999006.SH 测试半导体ETF 100 1.234", confidence=0.98, box=None),)
        ),
    )
    session = service.import_bytes(db_session, _image_bytes("PNG"), "image/png")
    assert session.status == "ready"
    assert db_session.query(HoldingImportCandidate).count() == 1
    assert db_session.query(Holding).count() == 0
    candidate = session.candidates[0]
    db_session.rollback()
    service.edit_candidate(db_session, session.session_id, candidate.id, {"selected_code": "999006.SH"})
    result = service.confirm(db_session, session.session_id)
    assert result["status"] == "confirmed"
    assert db_session.query(Holding).count() == 1


def test_holding_import_api_upload_review_edit_confirm_and_no_image_route(bootstrapped, tmp_path: Path, monkeypatch) -> None:
    from app.core.config import get_settings
    from app.main import app
    from app.services import holding_import_service
    from fastapi.testclient import TestClient

    monkeypatch.setattr(
        holding_import_service,
        "get_default_ocr_backend",
        lambda settings: FakeOCRBackend(
            lines=(OCRLine(text="512480.SH 半导体ETF 100 1.234", confidence=0.98, box=None),)
        ),
    )
    settings = Settings(_env_file=None, OCR_MODE="local_paddle", OCR_TRANSIENT_ROOT=tmp_path)
    app.dependency_overrides[get_settings] = lambda: settings
    monkeypatch.setattr("app.main.settings", settings)
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/holding-imports",
                files={"file": ("portfolio.png", _image_bytes("PNG"), "image/png")},
            )
            assert response.status_code == 201, response.text
            session_id = response.json()["session_id"]
            assert "storage_key" not in response.json()
            candidate = response.json()["candidates"][0]
            edit = client.patch(
                f"/api/holding-imports/{session_id}/candidates/{candidate['id']}",
                json={"selected_code": "512480.SH", "shares": 101, "cost_price": 1.235},
            )
            assert edit.status_code == 200, edit.text
            confirmed = client.post(f"/api/holding-imports/{session_id}/confirm")
            assert confirmed.status_code == 200, confirmed.text
            assert client.get(f"/api/holding-imports/{session_id}/image").status_code == 404

            rejected_import = client.post(
                "/api/holding-imports",
                files={"file": ("portfolio.png", _image_bytes("PNG"), "image/png")},
            )
            rejected_id = rejected_import.json()["session_id"]
            rejected_candidate = rejected_import.json()["candidates"][0]
            rejected = client.patch(
                f"/api/holding-imports/{rejected_id}/candidates/{rejected_candidate['id']}",
                json={"action": "reject"},
            )
            assert rejected.status_code == 200 and rejected.json()["status"] == "rejected"
            rejected_confirm = client.post(f"/api/holding-imports/{rejected_id}/confirm")
            assert rejected_confirm.status_code == 200, rejected_confirm.text
            assert rejected_confirm.json()["upserted"] == 0
    finally:
        app.dependency_overrides.pop(get_settings, None)


def test_holding_import_rejects_bad_upload_and_requires_auth() -> None:
    from app.main import app
    from fastapi.testclient import TestClient

    with TestClient(app) as client:
        response = client.post(
            "/api/holding-imports",
            files={"file": ("x.txt", b"not an image", "text/plain")},
            headers={"Authorization": "Bearer wrong"},
        )
        assert response.status_code == 415


def test_holding_import_resolver_classifies_exact_symbol_name_ambiguity_and_duplicates(db_session, tmp_path: Path) -> None:
    from app.models import Instrument
    from app.services.holding_import_service import HoldingImportService

    db_session.add_all(
        [
            Instrument(ts_code="999001.SH", symbol="999001", name="唯一沪深ETF", exchange="SH"),
            Instrument(ts_code="999002.SH", symbol="999002", name="独有半导体ETF", exchange="SH"),
            Instrument(ts_code="999002.SZ", symbol="999002", name="独有半导体ETF", exchange="SZ"),
        ]
    )
    db_session.flush()
    db_session.commit()
    service = HoldingImportService(
        Settings(_env_file=None, OCR_TRANSIENT_ROOT=tmp_path),
        ocr_backend=FakeOCRBackend(
            lines=(
                    OCRLine(text="999001 20 3.2", confidence=0.99, box=None),
                    OCRLine(text="唯一沪深ETF 30 3.3", confidence=0.99, box=None),
                    OCRLine(text="独有半导体ETF 40 1.2", confidence=0.99, box=None),
                OCRLine(text="未知基金 50 1.2", confidence=0.99, box=None),
                OCRLine(text="512480.SH 60 1.2", confidence=0.4, box=None),
                    OCRLine(text="999001.SH 70 3.5", confidence=0.99, box=None),
            )
        ),
    )
    session = service.import_bytes(db_session, _image_bytes("PNG"), "image/png")
    rows = session.candidates
    assert rows[0].match_status == "matched" and rows[0].ts_code == "999001.SH"
    assert rows[1].match_status == "duplicate" and rows[1].ts_code == "999001.SH"
    assert rows[2].match_status == "ambiguous"
    assert rows[2].safe_alternatives_json == ("999002.SH", "999002.SZ")
    assert rows[3].match_status == "unmatched" and rows[3].ts_code is None
    assert rows[4].match_status == "low_confidence"
    assert rows[5].match_status == "duplicate"
    assert rows[0].shares == Decimal("20") and rows[0].cost_price == Decimal("3.2")


def test_holding_import_existing_holding_is_duplicate_until_explicit_selection(db_session, tmp_path: Path) -> None:
    from app.models import Holding, Instrument
    from app.services.holding_import_service import HoldingImportService

    instrument = Instrument(ts_code="999003.SH", symbol="999003", name="沪深300ETF", exchange="SH")
    db_session.add(instrument)
    db_session.flush()
    db_session.commit()
    instrument = db_session.query(Instrument).filter_by(ts_code="999003.SH").one()
    db_session.add(Holding(instrument_id=instrument.id, shares=10, cost_price=3))
    db_session.flush()
    db_session.commit()
    service = HoldingImportService(
        Settings(_env_file=None, OCR_TRANSIENT_ROOT=tmp_path),
        ocr_backend=FakeOCRBackend(lines=(OCRLine(text="999003.SH 20 3.2", confidence=0.99, box=None),)),
    )
    session = service.import_bytes(db_session, _image_bytes("PNG"), "image/png")
    assert session.candidates[0].match_status == "duplicate"
    db_session.rollback()
    updated = service.edit_candidate(db_session, session.session_id, session.candidates[0].id, {"selected_code": "999003.SH"})
    assert updated.status == "reviewed"


def test_holding_import_confirm_is_atomic_and_idempotent(db_session, tmp_path: Path) -> None:
    from app.models import Instrument
    from app.services.holding_import_service import HoldingImportService

    db_session.add_all(
        [
            Instrument(ts_code="999004.SH", symbol="999004", name="沪深300ETF", exchange="SH"),
            Instrument(ts_code="999005.SH", symbol="999005", name="半导体ETF", exchange="SH"),
        ]
    )
    db_session.flush()
    db_session.commit()

    class FailingWriter:
        def __init__(self):
            self.calls = 0

        def upsert(self, db, **kwargs):
            self.calls += 1
            if self.calls == 2:
                raise RuntimeError("synthetic failure")
            return HoldingService().upsert(db, **kwargs)

    backend = FakeOCRBackend(
        lines=(
            OCRLine(text="999004.SH 20 3.2", confidence=0.99, box=None),
            OCRLine(text="999005.SH 30 1.2", confidence=0.99, box=None),
        )
    )
    failing = FailingWriter()
    service = HoldingImportService(Settings(_env_file=None, OCR_TRANSIENT_ROOT=tmp_path), ocr_backend=backend, holding_service=failing)
    session = service.import_bytes(db_session, _image_bytes("PNG"), "image/png")
    baseline_holding_count = db_session.query(Holding).count()
    db_session.rollback()
    for row in session.candidates:
        service.edit_candidate(db_session, session.session_id, row.id, {"selected_code": row.ts_code})
    db_session.commit()
    with pytest.raises(RuntimeError):
        service.confirm(db_session, session.session_id)
    db_session.rollback()
    assert db_session.query(Holding).count() == baseline_holding_count
    assert db_session.query(HoldingImportSession).filter_by(session_id=session.session_id).one().status == "ready"
    db_session.rollback()

    service = HoldingImportService(Settings(_env_file=None, OCR_TRANSIENT_ROOT=tmp_path), ocr_backend=backend)
    session = service.get(db_session, session.session_id)
    db_session.rollback()
    for row in session.candidates:
        service.edit_candidate(db_session, session.session_id, row.id, {"selected_code": row.ts_code})
    service.confirm(db_session, session.session_id)
    db_session.commit()
    repeated = service.confirm(db_session, session.session_id)
    assert repeated["status"] == "confirmed"
    assert db_session.query(Holding).count() == baseline_holding_count + 2


def test_holding_import_cancel_and_expiry_remove_only_opaque_storage(db_session, tmp_path: Path) -> None:
    from app.services.holding_import_service import HoldingImportService

    service = HoldingImportService(
        Settings(_env_file=None, OCR_TRANSIENT_ROOT=tmp_path),
        ocr_backend=FakeOCRBackend(),
    )
    session = service.import_bytes(db_session, _image_bytes("PNG"), "image/png")
    storage_dir = tmp_path / session.storage_key
    assert storage_dir.is_dir()
    result = service.cancel(db_session, session.session_id)
    db_session.commit()
    service.finalize_storage(session)
    assert result["status"] == "cancelled" and not storage_dir.exists()
    assert service.cancel(db_session, session.session_id)["status"] == "cancelled"

    second = service.import_bytes(db_session, _image_bytes("PNG"), "image/png")
    second_dir = tmp_path / second.storage_key
    db_session.rollback()
    db_session.query(HoldingImportSession).filter_by(session_id=second.session_id).update({"expires_at": datetime(2000, 1, 1, tzinfo=UTC)})
    db_session.commit()
    service.cleanup_expired(db_session, now=datetime.now(UTC))
    db_session.commit()
    db_session.expire_all()
    assert db_session.query(HoldingImportSession).filter_by(session_id=second.session_id).one().status == "expired" and not second_dir.exists()


def test_holding_import_cloud_consent_is_explicit_and_off_by_default(db_session, tmp_path: Path) -> None:
    from app.services.holding_import_service import HoldingImportConflict, HoldingImportService

    service = HoldingImportService(Settings(_env_file=None, OCR_TRANSIENT_ROOT=tmp_path), ocr_backend=FakeOCRBackend())
    session = service.import_bytes(db_session, _image_bytes("PNG"), "image/png")
    with pytest.raises(HoldingImportConflict, match="cloud review is disabled"):
        service.set_cloud_consent(db_session, session.session_id, True)
    assert session.cloud_consent is False


def test_holding_import_api_is_private_when_authentication_enabled(monkeypatch, tmp_path: Path) -> None:
    from app.core.config import get_settings
    from app.main import app
    from fastapi.testclient import TestClient

    settings = Settings(
        _env_file=None,
        auth_enabled=True,
        private_access_token="a" * 32,
        ocr_transient_root=tmp_path,
    )
    app.dependency_overrides[get_settings] = lambda: settings
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/holding-imports",
                files={"file": ("ignored.png", b"not-an-image", "image/png")},
            )
            assert response.status_code == 401
    finally:
        app.dependency_overrides.pop(get_settings, None)


def test_holding_import_api_rejects_oversized_multipart_stream() -> None:
    from app.main import app
    from fastapi.testclient import TestClient

    with TestClient(app) as client:
        response = client.post(
            "/api/holding-imports",
            files={"file": ("oversized.png", b"x" * (10 * 1024 * 1024 + 1), "image/png")},
        )
    assert response.status_code == 413


def test_holding_import_lifespan_cleanup_failure_does_not_block_startup(monkeypatch) -> None:
    from app.main import app
    from app.services.holding_import_service import HoldingImportService
    from fastapi.testclient import TestClient

    monkeypatch.setattr(HoldingImportService, "cleanup_expired", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("path")))
    with TestClient(app) as client:
        assert client.get("/api/health").status_code == 200


def test_holding_import_strict_name_and_invalid_exchange_never_fall_back(db_session, tmp_path: Path) -> None:
    from app.models import Instrument
    from app.services.holding_import_service import HoldingImportService

    db_session.add(Instrument(ts_code="999007.SH", symbol="999007", name="半导体ETF", exchange="SH"))
    db_session.flush()
    db_session.commit()
    service = HoldingImportService(
        Settings(_env_file=None, OCR_TRANSIENT_ROOT=tmp_path),
        ocr_backend=FakeOCRBackend(
            lines=(
                OCRLine(text="半导体ETF增强 10 1.2", confidence=0.99, box=None),
                OCRLine(text="999007.XX 半导体ETF 20 1.3", confidence=0.99, box=None),
            )
        ),
    )
    session = service.import_bytes(db_session, _image_bytes("PNG"), "image/png")
    assert session.candidates[0].match_status == "unmatched"
    assert session.candidates[0].ts_code is None
    assert session.candidates[1].match_status == "unmatched"
    assert session.candidates[1].ts_code is None


def test_holding_import_terminal_cleanup_clears_key_only_after_delete_and_retries(db_session, tmp_path: Path, monkeypatch) -> None:
    from app.services.holding_import_service import HoldingImportService

    service = HoldingImportService(Settings(_env_file=None, OCR_TRANSIENT_ROOT=tmp_path), ocr_backend=FakeOCRBackend())
    session = service.import_bytes(db_session, _image_bytes("PNG"), "image/png")
    db_session.commit()
    storage_dir = tmp_path / session.storage_key
    original_remove = service._remove_storage
    monkeypatch.setattr(service, "_remove_storage", lambda key: False)
    service.cancel(db_session, session.session_id)
    assert db_session.query(HoldingImportSession).filter_by(session_id=session.session_id).one().storage_key is not None
    monkeypatch.setattr(service, "_remove_storage", original_remove)
    service.cleanup_expired(db_session)
    db_session.expire_all()
    refreshed = db_session.query(HoldingImportSession).filter_by(session_id=session.session_id).one()
    assert refreshed.storage_key is None and not storage_dir.exists()


def test_holding_import_get_persists_expiry_before_return(db_session, tmp_path: Path) -> None:
    from app.services.holding_import_service import HoldingImportService

    service = HoldingImportService(Settings(_env_file=None, OCR_TRANSIENT_ROOT=tmp_path), ocr_backend=FakeOCRBackend())
    session = service.import_bytes(db_session, _image_bytes("PNG"), "image/png")
    db_session.rollback()
    db_session.query(HoldingImportSession).filter_by(session_id=session.session_id).update({"expires_at": datetime(2000, 1, 1, tzinfo=UTC)})
    db_session.commit()
    assert service.get(db_session, session.session_id).status == "expired"
    db_session.rollback()
    assert db_session.query(HoldingImportSession).filter_by(session_id=session.session_id).one().status == "expired"


def test_holding_import_api_get_persists_expiry_transition(db_session, tmp_path: Path, monkeypatch) -> None:
    from app.main import app
    from app.services import holding_import_service
    from app.services.holding_import_service import HoldingImportService
    from fastapi.testclient import TestClient

    settings = Settings(_env_file=None, OCR_TRANSIENT_ROOT=tmp_path)
    monkeypatch.setattr(
        holding_import_service,
        "get_default_ocr_backend",
        lambda current: FakeOCRBackend(),
    )
    monkeypatch.setattr("app.api.router.get_settings", lambda: settings)
    session = HoldingImportService(settings).import_bytes(db_session, _image_bytes("PNG"), "image/png")
    db_session.rollback()
    db_session.query(HoldingImportSession).filter_by(session_id=session.session_id).update({"expires_at": datetime(2000, 1, 1, tzinfo=UTC)})
    db_session.commit()
    with TestClient(app) as client:
        response = client.get(f"/api/holding-imports/{session.session_id}")
    assert response.status_code == 200 and response.json()["status"] == "expired"
    db_session.rollback()
    db_session.expire_all()
    assert db_session.query(HoldingImportSession).filter_by(session_id=session.session_id).one().status == "expired"


def test_holding_import_confirm_uses_conditional_transition_and_direct_service_transaction(db_session, tmp_path: Path) -> None:
    from app.models import Instrument
    from app.services.holding_import_service import HoldingImportConflict, HoldingImportService

    db_session.add(Instrument(ts_code="999008.SH", symbol="999008", name="CAS ETF", exchange="SH"))
    db_session.flush()
    db_session.commit()
    service = HoldingImportService(
        Settings(_env_file=None, OCR_TRANSIENT_ROOT=tmp_path),
        ocr_backend=FakeOCRBackend(lines=(OCRLine(text="999008.SH 12 1.2", confidence=0.99, box=None),)),
    )
    session = service.import_bytes(db_session, _image_bytes("PNG"), "image/png")
    service.edit_candidate(db_session, session.session_id, session.candidates[0].id, {"selected_code": "999008.SH"})
    db_session.commit()
    result = service.confirm(db_session, session.session_id)
    assert result["status"] == "confirmed"
    db_session.expire_all()
    assert db_session.query(HoldingImportSession).filter_by(session_id=session.session_id).one().status == "confirmed"
    db_session.rollback()
    assert service.confirm(db_session, session.session_id)["status"] == "confirmed"
    with pytest.raises(HoldingImportConflict):
        service.cancel(db_session, session.session_id)


def test_holding_import_confirming_state_blocks_a_second_writer(db_session, tmp_path: Path) -> None:
    from app.models import Instrument
    from app.services.holding_import_service import HoldingImportConflict, HoldingImportService

    db_session.add(Instrument(ts_code="999009.SH", symbol="999009", name="Concurrent ETF", exchange="SH"))
    db_session.flush()
    db_session.commit()
    service = HoldingImportService(
        Settings(_env_file=None, OCR_TRANSIENT_ROOT=tmp_path),
        ocr_backend=FakeOCRBackend(lines=(OCRLine(text="999009.SH 12 1.2", confidence=0.99, box=None),)),
    )
    session = service.import_bytes(db_session, _image_bytes("PNG"), "image/png")
    service.edit_candidate(db_session, session.session_id, session.candidates[0].id, {"selected_code": "999009.SH"})
    db_session.commit()
    db_session.query(HoldingImportSession).filter_by(session_id=session.session_id).update({"status": "confirming"})
    db_session.commit()
    with pytest.raises(HoldingImportConflict, match="already in progress"):
        service.confirm(db_session, session.session_id)


def test_holding_import_ttl_is_checked_at_cas_claim_and_never_upserts_after_clock_crossing(db_session, tmp_path: Path) -> None:
    from app.models import Instrument
    from app.services.holding_import_service import HoldingImportConflict, HoldingImportService

    db_session.add(Instrument(ts_code="999013.SH", symbol="999013", name="TTL ETF", exchange="SH"))
    db_session.flush()
    db_session.commit()
    now = [datetime.now(UTC)]
    service = HoldingImportService(
        Settings(_env_file=None, OCR_TRANSIENT_ROOT=tmp_path),
        ocr_backend=FakeOCRBackend(lines=(OCRLine(text="999013.SH 12 1.2", confidence=0.99, box=None),)),
        clock=lambda: now[0],
        before_claim=lambda: now.__setitem__(0, now[0] + timedelta(minutes=20)),
    )
    session = service.import_bytes(db_session, _image_bytes("PNG"), "image/png")
    service.edit_candidate(db_session, session.session_id, session.candidates[0].id, {"selected_code": "999013.SH"})
    with pytest.raises(HoldingImportConflict, match="expired"):
        service.confirm(db_session, session.session_id)
    db_session.expire_all()
    instrument_id = db_session.query(Instrument).filter_by(ts_code="999013.SH").one().id
    assert db_session.query(Holding).filter_by(instrument_id=instrument_id).count() == 0


def test_holding_import_write_failure_after_file_creation_leaves_no_orphan(db_session, tmp_path: Path, monkeypatch) -> None:
    from app.services.holding_import_service import HoldingImportService

    service = HoldingImportService(Settings(_env_file=None, OCR_TRANSIENT_ROOT=tmp_path), ocr_backend=FakeOCRBackend())
    original_commit = service._commit
    calls = 0

    def fail_initial_commit(current_db):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("synthetic commit failure")
        return original_commit(current_db)

    monkeypatch.setattr(service, "_commit", fail_initial_commit)
    with pytest.raises(RuntimeError):
        service.import_bytes(db_session, _image_bytes("PNG"), "image/png")
    assert list(tmp_path.iterdir()) == []


def test_holding_import_permission_failure_is_fail_closed_and_cleans_exact_storage(db_session, tmp_path: Path, monkeypatch) -> None:
    from app.services.holding_import_service import HoldingImportService, HoldingImportUnavailable

    service = HoldingImportService(Settings(_env_file=None, OCR_TRANSIENT_ROOT=tmp_path), ocr_backend=FakeOCRBackend())
    real_chmod = os.chmod

    def fail_chmod(path, mode):
        if str(path).endswith("source.img"):
            raise OSError("synthetic permission failure")
        return real_chmod(path, mode)

    monkeypatch.setattr("app.services.holding_import_service.os.chmod", fail_chmod)
    with pytest.raises(HoldingImportUnavailable):
        service.import_bytes(db_session, _image_bytes("PNG"), "image/png")
    assert list(tmp_path.iterdir()) == []


def test_holding_import_durable_processing_row_survives_ocr_crash_for_cleanup(db_session, tmp_path: Path) -> None:
    from app.services.holding_import_service import HoldingImportService

    class CrashingOCR:
        def recognize(self, image: bytes):
            del image
            raise KeyboardInterrupt()

    service = HoldingImportService(Settings(_env_file=None, OCR_TRANSIENT_ROOT=tmp_path), ocr_backend=CrashingOCR())
    with pytest.raises(KeyboardInterrupt):
        service.import_bytes(db_session, _image_bytes("PNG"), "image/png")
    row = (
        db_session.query(HoldingImportSession)
        .filter_by(status="processing")
        .order_by(HoldingImportSession.id.desc())
        .first()
    )
    assert row.status == "processing" and (tmp_path / row.storage_key).is_dir()
    row.expires_at = datetime(2000, 1, 1, tzinfo=UTC)
    db_session.commit()
    service.cleanup_expired(db_session)
    db_session.expire_all()
    assert db_session.query(HoldingImportSession).filter_by(id=row.id).one().status == "expired"


def test_holding_import_cleanup_does_not_commit_unrelated_caller_work(db_session, tmp_path: Path) -> None:
    from app.models import Instrument
    from app.services.holding_import_service import HoldingImportService

    service = HoldingImportService(Settings(_env_file=None, OCR_TRANSIENT_ROOT=tmp_path), ocr_backend=FakeOCRBackend())
    session = service.import_bytes(db_session, _image_bytes("PNG"), "image/png")
    db_session.rollback()
    db_session.query(HoldingImportSession).filter_by(session_id=session.session_id).update({"expires_at": datetime(2000, 1, 1, tzinfo=UTC)})
    db_session.commit()
    unrelated = Instrument(ts_code="999010.SH", symbol="999010", name="Unrelated", exchange="SH")
    db_session.add(unrelated)
    service.cleanup_expired(db_session)
    db_session.rollback()
    assert db_session.query(Instrument).filter_by(ts_code="999010.SH").one_or_none() is None
    db_session.expire_all()
    assert db_session.query(HoldingImportSession).filter_by(session_id=session.session_id).one().status == "expired"


def test_holding_import_cleanup_preserves_already_flushed_unrelated_work(db_session, tmp_path: Path) -> None:
    from app.models import Instrument
    from app.services.holding_import_service import HoldingImportService

    service = HoldingImportService(Settings(_env_file=None, OCR_TRANSIENT_ROOT=tmp_path), ocr_backend=FakeOCRBackend())
    session = service.import_bytes(db_session, _image_bytes("PNG"), "image/png")
    session.expires_at = datetime(2000, 1, 1, tzinfo=UTC)
    db_session.commit()
    unrelated = Instrument(ts_code="999014.SH", symbol="999014", name="Flushed unrelated", exchange="SH")
    db_session.add(unrelated)
    db_session.flush()
    service.cleanup_expired(db_session)
    # SQLite cannot have two writers while this caller transaction is open;
    # cleanup defers safely rather than touching caller state.
    assert db_session.get(Instrument, unrelated.id) is not None
    db_session.rollback()
    assert db_session.query(Instrument).filter_by(ts_code="999014.SH").one_or_none() is None


def test_holding_import_two_independent_sessions_race_one_cas_claim(db_session, tmp_path: Path) -> None:
    from app.db.session import SessionLocal
    from app.models import Instrument
    from app.services.holding_import_service import HoldingImportService

    db_session.add(Instrument(ts_code="999011.SH", symbol="999011", name="Race ETF", exchange="SH"))
    db_session.flush()
    db_session.commit()
    service = HoldingImportService(
        Settings(_env_file=None, OCR_TRANSIENT_ROOT=tmp_path),
        ocr_backend=FakeOCRBackend(lines=(OCRLine(text="999011.SH 12 1.2", confidence=0.99, box=None),)),
    )
    imported = service.import_bytes(db_session, _image_bytes("PNG"), "image/png")
    service.edit_candidate(db_session, imported.session_id, imported.candidates[0].id, {"selected_code": "999011.SH"})
    db_session.commit()
    barrier = threading.Barrier(2)
    outcomes: list[dict] = []

    def attempt() -> None:
        local_db = SessionLocal()
        try:
            local_service = HoldingImportService(
                Settings(_env_file=None, OCR_TRANSIENT_ROOT=tmp_path),
                ocr_backend=FakeOCRBackend(lines=()),
                before_claim=barrier.wait,
            )
            outcomes.append(local_service.confirm(local_db, imported.session_id))
        finally:
            local_db.close()

    threads = [threading.Thread(target=attempt) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
    assert len(outcomes) == 2
    assert all(item["status"] == "confirmed" for item in outcomes)
    db_session.expire_all()
    assert db_session.query(Holding).filter_by(instrument_id=db_session.query(Instrument).filter_by(ts_code="999011.SH").one().id).count() == 1


def test_holding_import_confirm_writes_selected_codes_in_deterministic_order(db_session, tmp_path: Path) -> None:
    from app.models import Instrument
    from app.services.holding_import_service import HoldingImportService

    db_session.add_all(
        [
            Instrument(ts_code="999015.SH", symbol="999015", name="Order A", exchange="SH"),
            Instrument(ts_code="999016.SH", symbol="999016", name="Order B", exchange="SH"),
        ]
    )
    db_session.flush()
    db_session.commit()
    order: list[str] = []

    class RecordingWriter:
        def upsert(self, db, **kwargs):
            order.append(kwargs["ts_code"])
            return HoldingService().upsert(db, **kwargs)

    service = HoldingImportService(
        Settings(_env_file=None, OCR_TRANSIENT_ROOT=tmp_path),
        ocr_backend=FakeOCRBackend(
            lines=(
                OCRLine(text="999016.SH 12 1.2", confidence=0.99, box=None),
                OCRLine(text="999015.SH 10 1.1", confidence=0.99, box=None),
            )
        ),
        holding_service=RecordingWriter(),
    )
    session = service.import_bytes(db_session, _image_bytes("PNG"), "image/png")
    for candidate in session.candidates:
        service.edit_candidate(db_session, session.session_id, candidate.id, {"selected_code": candidate.ts_code})
    service.confirm(db_session, session.session_id)
    assert order == ["999015.SH", "999016.SH"]


def test_holding_import_mutations_fail_closed_with_flushed_caller_transaction(db_session, tmp_path: Path) -> None:
    from app.models import Instrument
    from app.services.holding_import_service import HoldingImportConflict, HoldingImportService

    db_session.add(Instrument(ts_code="999017.SH", symbol="999017", name="Isolation ETF", exchange="SH"))
    db_session.flush()
    db_session.commit()
    service = HoldingImportService(
        Settings(_env_file=None, OCR_TRANSIENT_ROOT=tmp_path),
        ocr_backend=FakeOCRBackend(lines=(OCRLine(text="999017.SH 12 1.2", confidence=0.99, box=None),)),
    )
    session = service.import_bytes(db_session, _image_bytes("PNG"), "image/png")
    db_session.rollback()
    unrelated = Instrument(ts_code="999018.SH", symbol="999018", name="Caller Work", exchange="SH")
    db_session.add(unrelated)
    db_session.flush()
    blocked_root = tmp_path / "blocked"
    blocked_service = HoldingImportService(
        Settings(_env_file=None, OCR_TRANSIENT_ROOT=blocked_root),
        ocr_backend=FakeOCRBackend(),
    )
    with pytest.raises(HoldingImportConflict, match="caller transaction"):
        blocked_service.import_bytes(db_session, _image_bytes("PNG"), "image/png")
    assert not blocked_root.exists()
    with pytest.raises(HoldingImportConflict, match="caller transaction"):
        service.edit_candidate(db_session, session.session_id, session.candidates[0].id, {"selected_code": "999017.SH"})
    with pytest.raises(HoldingImportConflict, match="caller transaction"):
        service.confirm(db_session, session.session_id)
    assert db_session.get(Instrument, unrelated.id) is not None
    db_session.rollback()
    assert db_session.query(Instrument).filter_by(ts_code="999018.SH").one_or_none() is None
    assert (tmp_path / session.storage_key).is_dir()


def test_holding_import_mutations_fail_closed_for_sqlite_memory_database(tmp_path: Path) -> None:
    from app.db.base import Base
    from app.services.holding_import_service import HoldingImportConflict, HoldingImportService
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        service = HoldingImportService(Settings(_env_file=None, OCR_TRANSIENT_ROOT=tmp_path), ocr_backend=FakeOCRBackend())
        with pytest.raises(HoldingImportConflict, match="file-backed database"):
            service.import_bytes(db, _image_bytes("PNG"), "image/png")


def test_holding_import_boxed_cells_sort_left_to_right_under_vertical_jitter(db_session, tmp_path: Path) -> None:
    from app.models import Instrument
    from app.services.holding_import_service import HoldingImportService

    db_session.add(Instrument(ts_code="999019.SH", symbol="999019", name="Jitter ETF", exchange="SH"))
    db_session.flush()
    db_session.commit()

    def cell(text: str, left: float, top: float, right: float) -> OCRLine:
        return OCRLine(text=text, confidence=0.98, box=OCRBox(points=((left, top), (right, top), (right, top + 10), (left, top + 10))))

    service = HoldingImportService(
        Settings(_env_file=None, OCR_TRANSIENT_ROOT=tmp_path),
        ocr_backend=FakeOCRBackend(
            lines=(
                cell("1.234", 250, 1.5, 290),
                cell("999019.SH", 0, 0, 80),
                cell("120", 200, 0.5, 230),
                cell("Jitter ETF", 90, 1, 180),
            )
        ),
    )
    row = service.import_bytes(db_session, _image_bytes("PNG"), "image/png").candidates[0]
    assert row.ts_code == "999019.SH" and row.name == "Jitter ETF"
    assert row.shares == Decimal("120") and row.cost_price == Decimal("1.234")


def test_holding_import_assembles_boxed_table_cells_left_to_right_without_name_digits_becoming_shares(db_session, tmp_path: Path) -> None:
    from app.models import Instrument
    from app.services.holding_import_service import HoldingImportService

    db_session.add(Instrument(ts_code="999012.SH", symbol="999012", name="中证500ETF", exchange="SH"))
    db_session.flush()
    db_session.commit()
    def cell(text: str, left: float, top: float, right: float, confidence: float = 0.98) -> OCRLine:
        return OCRLine(
            text=text,
            confidence=confidence,
            box=OCRBox(points=((left, top), (right, top), (right, top + 10), (left, top + 10))),
        )

    service = HoldingImportService(
        Settings(_env_file=None, OCR_TRANSIENT_ROOT=tmp_path),
        ocr_backend=FakeOCRBackend(
            lines=(
                cell("999012.SH", 0, 0, 80),
                cell("中证500ETF", 90, 0, 180),
                cell("120", 200, 0, 230),
                cell("1.234", 250, 0, 290),
            )
        ),
    )
    session = service.import_bytes(db_session, _image_bytes("PNG"), "image/png")
    candidate = session.candidates[0]
    assert candidate.ts_code == "999012.SH"
    assert candidate.name == "中证500ETF"
    assert candidate.shares == Decimal("120")
    assert candidate.cost_price == Decimal("1.234")


def test_paddle_worker_box_projection_preserves_rectangles_and_polygons() -> None:
    from app.ocr.paddle_adapter import _safe_box

    assert _safe_box([0, 2, 40, 12]) == ((0.0, 2.0), (40.0, 2.0), (40.0, 12.0), (0.0, 12.0))
    assert _safe_box([[0, 2], [40, 2], [40, 12], [0, 12]]) == ((0.0, 2.0), (40.0, 2.0), (40.0, 12.0), (0.0, 12.0))
    assert _safe_box([-1, 2, 40, 12]) is None
