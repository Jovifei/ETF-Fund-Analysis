# Provider-Neutral Analysis Gateway Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a single-primary, provider-neutral analysis gateway with Codex/OpenAI Responses, Anthropic Messages, and DeepSeek-compatible adapters while keeping model output out of deterministic scores and signals.

**Architecture:** Typed contracts enforce an allowlisted input bundle and structured text-only output. Exactly one configured direct adapter runs; failures persist `analysis_unavailable` and never trigger silent provider or heuristic substitution. Agent runners create read-only review candidates only.

**Tech Stack:** FastAPI, Pydantic v2, httpx, SQLAlchemy 2, Alembic, pytest.

---

### Task A1: Contracts and configuration

**Files:**
- Create: `backend/app/analysis/__init__.py`
- Create: `backend/app/analysis/contracts.py`
- Create: `backend/tests/test_analysis_config.py`
- Modify: `backend/app/core/config.py`

- [x] **RED:** Add tests proving exactly one active primary, a missing primary key/model is rejected, and `AnalysisOutput` rejects numeric decision fields and unknown fields.

```python
def test_analysis_output_rejects_model_computed_decision_fields():
    with pytest.raises(ValidationError):
        AnalysisOutput.model_validate({
            "facts": [], "inferences": [], "risk_flags": [],
            "affected_themes": [], "impact_horizon": "1w",
            "evidence_ids": [], "confidence_statement": "low",
            "impact_score": 90,
        })
```

- [x] Run `python -m pytest -q backend/tests/test_analysis_config.py`; observed RED because contracts/settings did not exist.
- [x] Implement `VerifiedAnalysisInput`, `AnalysisOutput`, `AnalysisEnvelope`, provider/status enums, deterministic input/output hashes, `extra="forbid"`, and a Protocol for `analyze()`.
- [x] Add `ANALYSIS_PRIMARY_PROVIDER/MODEL/MODE/PROMPT_VERSION`, per-provider base URLs/enabled/timeouts, and validators. Keep legacy `LLM_*` fields as a compatibility bridge for one release without logging secrets.
- [x] Run the focused tests; observed 50 passed after review fixes.
- [x] Run `python -m compileall -q backend/app`.
- [x] Controller checkpoint only; no stage/commit.

### Task A2: Direct adapters and gateway behavior

**Files:**
- Create: `backend/app/analysis/adapters.py`
- Create: `backend/app/services/analysis_service.py`
- Create: `backend/tests/test_analysis_gateway.py`

- [x] **RED:** Use `httpx.MockTransport` to assert OpenAI Responses, Anthropic Messages, and DeepSeek-compatible payload/header parsing; assert no request contains `tools`, credentials in body, price/return/probability/trade fields, or silent retry to another adapter. The RED was reconstructed after an environment setup error and remains a documented process caveat.
- [x] Run focused tests with the correct Python 3.12 environment.
- [x] Implement httpx-based adapters with provider-safe strict schema, bounded input/output/timeout, client lifecycle, and strict parsing. Codex/OpenAI uses `/responses`; Anthropic uses `/v1/messages`; DeepSeek-compatible uses `/chat/completions`.
- [x] Implement a registry that selects exactly the configured primary. On network/schema failure, return `analysis_unavailable` or `invalid_response` with sanitized exception class and no second-provider call.
- [x] Run focused/full tests, compileall, Node syntax, ruff and diff check; final quality review found no Critical/Important issue.
- [x] Controller checkpoint only; no commit.

### Task A3a: Persistence and review-candidate records

**Files:**
- Create: `backend/alembic/versions/9f1c2b3a4d5e_multi_model_analysis.py`
- Create: `backend/app/services/review_service.py`
- Create: `backend/tests/test_analysis_persistence.py`
- Modify: `backend/app/models/entities.py`
- Modify: `backend/app/models/__init__.py`

- [x] **RED:** Add tests for `AnalysisRun` provenance, persisted `analysis_unavailable`, immutable bundle/result hashes, and review-candidate enqueue/accept/reject without subprocess execution.
- [x] Run focused tests and observe missing persistence/models RED.
- [x] Add `analysis_runs` and `agent_review_candidates` with immutable canonical payload/hash, provider/model/prompt/schema/status/latency/result/sanitized error and explicit acceptance fields. Add nullable NewsItem link/provenance without storing secrets.
- [x] Implement ReviewService atomic record lifecycle only; no Codex/Claude CLI launch.
- [x] Run focused/full tests, compileall, ruff, diff check, SQLite Alembic upgrade/downgrade/upgrade, raw UPDATE/DELETE and race probes. PostgreSQL execution remains a deployment gate.
- [x] Controller checkpoint only; no commit.

### Task A3b1: News, signal, and Dashboard integration

**Files:**
- Modify: `backend/app/services/news_service.py`
- Modify: `backend/app/services/llm_service.py`
- Modify: `backend/app/services/signal_service.py`
- Modify: `backend/app/services/dashboard_service.py`
- Create: `backend/tests/test_news_analysis.py`
- Modify: `backend/tests/test_analysis_persistence.py`

- [x] **RED:** Add tests for no heuristic masquerading as a model result, deterministic `NewsItem.impact_score`, completed/unavailable analysis provenance, no model numeric signal authority, and Dashboard analysis status fields.
- [x] Run focused tests and observe missing integration RED.
- [x] Integrate the gateway into news refresh and existing-news analysis. Preserve deterministic heuristic impact fields for SignalService; model output stays in AnalysisRun candidate commentary. A failed model analysis is visible as unavailable.
- [x] Make `llm_service.py` a compatibility façade without a second direct HTTP implementation.
- [x] Run focused/full tests, compileall, Node syntax, ruff, integrity/Mock/provider-failure/reuse probes; final quality review found no Critical/Important.
- [x] Controller checkpoint only; no commit.

### Task A3b2: Review API and task integration

**Files:**
- Modify: `backend/app/api/schemas.py`
- Modify: `backend/app/api/router.py`
- Modify: `backend/app/services/task_service.py`
- Modify: `backend/tests/test_analysis_persistence.py`

- [x] **RED:** Add tests for direct-analysis task behavior and private review-candidate enqueue/list/accept/reject API status changes.
- [x] Run focused tests and observe missing API/task/transaction behavior.
- [x] Add private read/enqueue/accept/reject endpoints for candidate review records; do not launch Codex/Claude Code CLI from the application.
- [x] Add run-id alignment, gateway provenance guard, bounded task input, durable failed TaskRun audit and partial pipeline semantics.
- [x] Run focused/full tests, compileall, Node syntax, ruff and API/transaction/integrity probes; final quality review found no Critical/Important.
- [x] Controller checkpoint only; no commit.
