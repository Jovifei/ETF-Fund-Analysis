# Market Context Backend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a separately modeled market-context registry and snapshots for China sectors, S&P 500, Nasdaq Composite, Nasdaq-100, and verified China/Korea semiconductor ETF proxies.

**Architecture:** Foreign indices and sector breadth stay outside the ETF/LOF Instrument table. Registry items are always renderable, while observations are written only for enabled and verified capabilities. Unverified proxy codes remain null/disabled and visibly unavailable.

**Tech Stack:** JSON configuration, provider contracts, SQLAlchemy/Alembic, FastAPI task pipeline, pytest.

---

### Task B1: Registry, contracts, and schema

**Files:**
- Create: `config/market_context.json`
- Create: `backend/alembic/versions/a2b3c4d5e6f7_market_context.py`
- Create: `backend/tests/test_market_context.py`
- Modify: `backend/app/core/config.py`
- Modify: `backend/app/providers/types.py`
- Modify: `backend/app/providers/base.py`
- Modify: `backend/app/models/entities.py`
- Modify: `backend/app/models/__init__.py`

- [x] **RED:** Test unique context IDs/display order, six required default items, distinct S&P/Nasdaq identifiers, null+disabled+unverified China/Korea proxy codes, and rejection of an enabled unverified proxy.
- [x] Run focused tests and observe missing registry/contracts/schema RED.
- [x] Add strict `MarketContextObservation`, capability-unavailable contract, registry loader/validator, `MarketContextRegistry`, and `MarketContextSnapshot`.
- [x] Snapshot stores observed level/optional price, today pct change, aware source/fetched timestamps, source, freshness, verified/Mock/degraded state, and an idempotent uniqueness key with adversarial DB checks.
- [x] Implement migration with down revision `9f1c2b3a4d5e`.
- [x] Run focused/full tests and Alembic upgrade/downgrade/upgrade; final quality review found no Critical/Important.
- [x] Controller checkpoint only; no commit.

### Task B2a: Registry sync and Provider observations

**Files:**
- Create: `backend/app/services/market_context_service.py`
- Modify: `backend/app/providers/mock.py`
- Modify: `backend/app/providers/composite.py`
- Modify: `backend/tests/test_market_context.py`

- [ ] **RED:** Test disabled/unverified registry visibility with zero provider calls, eligible verified observations, Mock/degraded provenance, idempotent snapshots, and real capability unavailable without fallback.
- [ ] Run focused tests; expected RED.
- [ ] Implement registry sync, eligible request construction, provider observation validation, idempotent snapshot writes and latest-view query. Emit no task/event yet.
- [ ] Run focused/full tests, compileall, ruff and diff check.
- [ ] Controller checkpoint only; no commit.

### Task B2b: Task, scheduler, Dashboard, and API payload

**Files:**
- Modify: `backend/app/services/task_service.py`
- Modify: `backend/app/scheduler.py`
- Modify: `backend/app/services/dashboard_service.py`
- Modify: `backend/app/api/router.py`
- Modify: `backend/tests/test_api.py`
- Modify: `backend/tests/test_pipeline.py`
- Modify: `backend/tests/test_market_context.py`

- [ ] **RED:** Test task/event/scheduler behavior, private context endpoint/bootstrap payload, registry-only unverified rows, and full forecast provenance fields.
- [ ] Run focused tests; expected RED.
- [ ] Add task name `refresh_market_context`, scheduler cadence, event emission, private bootstrap/API payload and partial-pipeline behavior.
- [ ] Extend forecast payload with `as_of_date`, generation time, model version, calibration, sample count, p-up, expected return, q10/q50/q90, and data cutoff where available.
- [ ] Run focused tests, all tests, compileall, and Node syntax; expected GREEN.
- [ ] Controller checkpoint only; no commit.
