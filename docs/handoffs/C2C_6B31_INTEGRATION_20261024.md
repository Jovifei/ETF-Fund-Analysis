# C2C integration handoff — c2c_6b31 — 2026-10-24

Status: IMPLEMENTED / CI_ACCEPTANCE_PENDING at commit time. This document deliberately does **not** assert future GitHub Actions success. The fixed SHA and tree must be read directly from GitHub PR54/branch after a finished run.

## Inputs and code boundary

GitHub-only authorized branch: `codex/c2c-6b31-integrated-20261024`, PR54 targets main as **Draft**. Parent/base source is exact PR52 `ea6e965ae5a8e49f204e8dcf5bb065072ffd4fdc` (merge of docs consolidation and PR51 `f6d0d332ab8bd27f34cb573b31a141f32cc57bac`). Main base `1a4b6652f49c412145d12812fa02820ba0a80991`; PR53 final `fdaf5426585d64800dbff60656797cd75306f19e`; this integration's test-first RED receipt is committed as the prior parent `64e9c5db11229dbb6825aa5ce0b8e3cf3074c433`. Full RED diagnosis: [audit](../audits/C2C_6B31_RED_INTEGRATION_20261024.md).

Only two test files and two new audit/handoff documents differ from exact PR52. No production code, configs, strategy, Provider, account/holding, private data, dependency/lockfile, CI workflow or deployment was changed on this branch. Existing three PR branches and main untouched.

## Implementation choices

1. `frontend/e2e-auth/local-display-consumption.spec.ts` — authenticated controlled-replay fixture now supplies `local-display-context-read-v1` and provenance times as actual local Reader/API does. Keep generation 101 pin and status assertions, verify account authentication, prevent cloud writes. Do **not** click a phantom index-OHLC action in `local_bundle`; assert index card is noninteractive, display says history is unpublished, chart entry stays absent, and no index chart request occurs. Retain 1/3/7/20/60 supported horizons and ETF detail's read-only guard. This fixes a CI test/consumer-contract mismatch; it does not mislabel real provider data or change server authorization.
2. `backend/tests/test_display_cache_rolling.py` — preserve PR51's `watch_atomic_peak` wrapping `os.replace` to assert `used_bytes + held_bytes <= cap` at the temporary-file peak, three-generation forced retention and 8KiB pointer headroom plus 1024B chunk hold. Fold in PR53 final `fdaf542` invariants: exact retained generation count, zero held bytes after commit, explicit second/previous generations protected and charged used/held cap. **Do not replace PR51's stronger file wholesale** or change production quota/accounting.

## Verification commands and expected evidence

- Backend full CI: `pytest -q`; `python -m compileall -q backend/app scripts`; `node --check backend/app/static/app.js`; migration/secret/shell/Compose/container smoke according to existing `ci.yml`.
- Frontend security: `npm ci --ignore-scripts --prefix frontend`; `npm audit --audit-level=high --prefix frontend` (Vite pinned 7.3.7); `npm --prefix frontend run typecheck`; `npm --prefix frontend test`; `npm --prefix frontend run build`.
- Actual browser: `npm --prefix frontend run test:e2e`; `cd frontend && npx playwright test --config playwright.auth.config.ts`; `cd frontend && npx playwright test --config playwright.responsive.config.ts`.
- Other existing `audit-platforms` and `postdeploy-ci` tests; postdeploy-ci is a **testing** workflow here, not production.
- GitHub Actions CI must be bound to new branch's exact SHA/tree, not PR51/52/53 heads, and all failing/skipped steps reported. The `frontend/e2e-auth` controlled test uses synthetic mocks and disposable local test authentication, not production credentials or a human-logged-in site.
- No merge/deploy until independent Owner approval and real acceptance. Natural 2 trading days, actual settled daily bars, cloud zero-growth, production auth/phone, data/license/units/PIT/OOS/calibration remain **PENDING/UNKNOWN**; `actionable=false`, `not_calibrated` preserved.

## Review checklist

- Review PR54 diff against PR52, confirm exactly two test files + 2 docs and no production diff since parent.
- Confirm checkout tree and dependencies Vite7.3.7; validate frontend mock has `read_contract` and no forbidden write calls.
- Confirm rolling peak watcher still installed and assertions do not hide errors by enlarging runtime quota.
- Read back GitHub branch SHA/tree, latest `ci`, `workspace-ci`, `audit-platforms`, `postdeploy-ci` and original PR refs before giving local fixed-SHA handoff.

Hub report NOT_SENT: Windows-only Owner CLI inaccessible without the C2C tunnel; no false claim. No live provider queries, no credentials, no production files.
