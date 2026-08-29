# Portfolio OCR Import Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add private screenshot-based holding import with local PaddleOCR, transient storage, code/name resolution, editable candidates, and explicit confirmation before any holding write.

**Architecture:** Image validation and OCR backends are isolated behind contracts. Source images live only in a bounded private transient directory; normal records contain hashes/confidence/status, never pixels or raw OCR payload. The existing HoldingService remains the only final holding writer.

**Tech Stack:** FastAPI UploadFile, Pillow validation, optional PaddleOCR adapter, SQLAlchemy/Alembic, pytest fake OCR backend.

---

### Task C1: Image/OCR contracts, configuration, and schema

**Files:**
- Create: `backend/app/ocr/__init__.py`
- Create: `backend/app/ocr/contracts.py`
- Create: `backend/app/ocr/image_validation.py`
- Create: `backend/app/ocr/paddle_adapter.py`
- Create: `backend/app/ocr/fake.py`
- Create: `backend/alembic/versions/b3c4d5e6f7a8_holding_import.py`
- Create: `backend/tests/test_holding_import.py`
- Modify: `backend/app/core/config.py`
- Modify: `backend/app/models/entities.py`
- Modify: `backend/app/models/__init__.py`
- Modify: `pyproject.toml`

- [ ] **RED:** Add synthetic image tests for valid PNG/JPEG/WebP, MIME/magic mismatch, decode failure, bytes+1 limit, dimensions/decompression bomb, lazy unavailable Paddle backend, and no network/model download.
- [ ] Run focused tests; expected RED.
- [ ] Add Pillow to the bounded image-validation dependency path and an optional PaddleOCR extra. Paddle imports lazily and requires a configured local model directory; missing packages/models return `ocr_unavailable`.
- [ ] Add validated OCR result/line/box/confidence contracts and a deterministic fake backend.
- [ ] Add settings for local mode, cloud-review disabled, transient root, 15-minute TTL, byte/dimension/time limits, and local model path.
- [ ] Add import-session/candidate entities and migration down revision `a2b3c4d5e6f7`; never store image bytes or full raw OCR payload.
- [ ] Run focused tests and clean Alembic upgrade; expected GREEN.
- [ ] Controller checkpoint only; no commit.

### Task C2: Import service and private API

**Files:**
- Create: `backend/app/services/holding_import_service.py`
- Modify: `backend/app/api/schemas.py`
- Modify: `backend/app/api/router.py`
- Modify: `backend/app/main.py`
- Modify: `backend/tests/test_holding_import.py`

- [ ] **RED:** Test exact ts_code, six-digit+exchange, configured-name resolution, ambiguous/unmatched/low-confidence/duplicate states, no holding before confirm, one deterministic upsert after confirm, idempotent confirm, reject/cancel/expiry cleanup, private auth, and no source-image retrieval endpoint.
- [ ] Run focused tests; expected RED.
- [ ] Implement bounded UploadFile reads, opaque session directories under a resolved transient root, OCR execution, parser/resolver, field confidence, editable candidates, explicit confirm/cancel, and cleanup at startup/request boundaries.
- [ ] Confirmation rejects unresolved candidates and calls existing `HoldingService.upsert` inside one transaction. Cloud review remains a consent/status interface only and cannot save holdings.
- [ ] Close image/OCR handles before Windows cleanup; never derive paths from user filenames.
- [ ] Run focused tests, all tests, compileall, secret scan, and Node syntax; expected GREEN.
- [ ] Controller checkpoint only; no commit.
