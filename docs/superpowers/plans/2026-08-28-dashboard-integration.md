# Dashboard and Release Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver the approved Dashboard hierarchy, OCR review interaction, versioned documentation, and full-system validation without changing strategy formulas or promoting unverified data.

**Architecture:** The private bootstrap payload remains the page's source of truth. Frontend rendering uses separate context/observed/forecast surfaces and code-first identity. OCR uses FormData upload and an explicit candidate review state before confirmation.

**Tech Stack:** Vanilla HTML/CSS/JavaScript, FastAPI static app, Jinja2 report, pytest, Node syntax, local browser smoke.

---

### Task D1: Market, identity, and forecast UI

**Files:**
- Modify: `backend/app/static/index.html`
- Modify: `backend/app/static/app.js`
- Modify: `backend/app/static/app.css`
- Modify: `backend/app/templates/report.html.j2`
- Modify: `backend/tests/test_api.py`
- Modify: `backend/tests/test_pipeline.py`

- [ ] **RED:** Add payload/static assertions for a default market-context section, code-first identity in instrument/holding/detail/report, today pct-change before price, and forecast labels/classes/provenance distinct from observed quote classes.
- [ ] Run focused tests; expected RED.
- [ ] Implement context cards for China sectors, S&P 500, Nasdaq Composite, Nasdaq-100, and visible unverified China/Korea proxy cards. Never fabricate proxy codes or observations.
- [ ] Implement `displayIdentity(code, name)`; make today change primary and price/source/time secondary.
- [ ] Implement dedicated forecast surface `FORECAST · 非实际结果` with horizon, model, cutoff, samples, interval, and calibration.
- [ ] Run focused tests, all tests, and `node --check backend/app/static/app.js`; expected GREEN.
- [ ] Controller checkpoint only; no commit.

### Task D2: Portfolio OCR review UI

**Files:**
- Modify: `backend/app/static/index.html`
- Modify: `backend/app/static/app.js`
- Modify: `backend/app/static/app.css`
- Modify: `backend/tests/test_api.py`

- [ ] **RED:** Add static/API assertions for PNG/JPEG/WebP input, FormData without JSON Content-Type, candidate review rows, confidence/status badges, edit/reject, explicit confirm/cancel, and cloud consent warning.
- [ ] Run focused tests; expected RED.
- [ ] Add upload/review modal and client session state. Update `api()` so FormData preserves the browser multipart boundary while Authorization remains header-only.
- [ ] Render standard ETF code first, low-confidence/ambiguous/duplicate warnings, and prohibit confirm until selected rows are resolved.
- [ ] Run focused tests, all tests, and Node syntax; expected GREEN.
- [ ] Controller checkpoint only; no commit.

### Task D3: Version, docs, migrations, and end-to-end validation

**Files:**
- Modify: `backend/app/core/config.py`
- Modify: `pyproject.toml`
- Modify: `deploy/.env.production.example`
- Modify: `README.md`
- Modify: `QUICKSTART.md`
- Modify: `docs/ARCHITECTURE.md`
- Modify: `docs/IMPLEMENTATION_MATRIX.md`
- Modify: `STATUS.md`
- Modify: `HANDOFF.md`
- Modify: `tasks/todo.md`

- [ ] Set application/package release version to `0.6.0`; keep deterministic signal/indicator/forecast versions unchanged unless their formulas/data contracts were actually changed.
- [ ] Document one-primary analysis provider, no silent failover, no tools, manual provider switching, read-only agent runners, local OCR provisioning, cloud consent, market-context verification, and migration/deployment steps.
- [ ] Run a clean Alembic upgrade from zero and inspect the three new revisions.
- [ ] Run `pytest -q`, `python -m compileall -q backend/app`, `node --check backend/app/static/app.js`, three Git Bash syntax checks, scoped secret scan, Mock bootstrap, and local HTTP/browser smoke.
- [ ] Verify no API/log/report contains credentials, image paths, raw OCR text, or untrusted provider exception details.
- [ ] Record exact changed files, tests, Mock-only boundaries, Paddle runtime qualification status, and real-provider blockers in `tasks/todo.md`.
- [ ] Controller checkpoint only; no commit/push.
