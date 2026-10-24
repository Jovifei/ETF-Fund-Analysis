# c2c_6b31 — final fixed-SHA GitHub integration handoff (2026-10-24)

**PR:** 54, Draft; `codex/c2c-6b31-integrated-20261024`. This file is SHA-agnostic by design: read the true final HEAD/tree from GitHub PR54 and its final CI after completion. **Never merge or deploy automatically.**

## Stage identity, sequential failing-test-first evidence

- Base `main`: `1a4b6652f49c412145d12812fa02820ba0a80991` (unchanged).
- PR51 latest freeze: `bdb556f9c60254b2e8e866f256386b062e2ab7ab`.
- PR52 latest freeze: `109253e8c4ccb5c7c8e21b22d0911398cd8beb16` / tree `7e0e9b83f09067b757746e4a5caae2c879823254`, containing newest PR51 and consolidated docs/Vite 7.3.7.
- PR53 final: `fdaf5426585d64800dbff60656797cd75306f19e`; its receiver/browser fixes through `f89b382` are in PR52 ancestry; its final rolling fixture assertions are **merged semantically into** PR51's stronger peak test, not by overwriting it.
- This task's first parent is `0b63ce4bf0d468d5b816017ff3ee785ca4eebb55` (GitHub four-workflow SUCCESS; original RED audit first commit `64e9c5db11229dbb6825aa5ce0b8e3cf3074c433`); second parent is latest PR52 `109253e8`. New merged tree is built from the second parent's exact tree and overlays only the reviewed rolling test and this task's audit/handoff docs, preserving all Owner changes.
- Initial test-first RED: unchanged PR52 `ea6e965a`, `workspace-ci` `40051857466`, 228 Vue PASS / 44 mock Chromium PASS / 5 auth PASS / 1 auth FAIL: `market-context-status` absent (mock missing `read_contract`) and latent clickable-index expectation. Earlier controlled fixture repair in this branch is retained in ancestry; final tree adopts Owner's **stronger** updated auth browser tests, including honest timestamps/historical/expired labels, pinned instrument/chart, absence of index/minute history and zero workspace writes.
- Additional current-Windows test evidence / scope: [audit](../audits/C2C_6B31_WINDOWS_FINAL_FREEZE_20261024.md); former review [reconciliation](../audits/C2C_6B31_LATEST_RECONCILIATION_20261024.md); initial RED [receipt](../audits/C2C_6B31_RED_INTEGRATION_20261024.md).

## Code/tree delta relative to latest PR52

Expected small delta: **only** `backend/tests/test_display_cache_rolling.py` plus the c2c_6b31 audit/handoff Markdown files. The rolling test still has PR51's `watch_atomic_peak` at `os.replace`, `used_bytes+held_bytes<=max`, 8KiB synthetic pointer headroom +1024B staged receipt reserve, `max_generations=3`, and negative rollback. Add PR53 fdaf final `held_bytes==0` at completion, protected previous/second generation and exact retention count. No changes to production `SyncDomain`, `LocalDisplayStore`, quotas, deadlines or other runtime source beyond the already inherited PR51/52 code.

Latest PR52 additionally includes an isolated **test-only** Windows OCR spawn worker (`backend/tests/_ocr_workers.py`) and corresponding test `test_holding_import.py` adjustment; this is inherited **unchanged**. The original Windows full run had 1 failure; Owner documented focused corrected tests, but GitHub Windows bridge coverage is **not** full Windows pytest. Do not convert that historical RED or prior Ubuntu CI into current Windows full-pass approval.

No writes to original PR51/52/53 branch refs, `main`, protected Owner working tree, production, strategy, Provider, accounts, holdings, private DB, credentials or deployment. Repository access/writes through the GitHub plugin only; C2C tunnel deliberately not called.

## CI matrix and decision gates

On the **new exact PR54 head SHA/tree** run/review existing GitHub Actions:
1. `ci.yml` full backend `pytest -q`, Python compile, Node checks/tests, secret scan, Alembic, shellcheck/Compose, Docker source inventory and isolated image smoke.
2. `workspace-ci.yml` npm audit-high (Vite 7.3.7), Workspace backend, TypeScript, Vue, frontend build, Mock/authenticated/responsive Playwright.
3. `audit-platforms.yml` PostgreSQL/Windows bridge.
4. `postdeploy-ci.yml` follow-up contracts/Windows archive (the workflow name does **not** mean deploy).

The previous integrated `0b63ce4b` **passed** all four workflows; JUnit 2638 total, 2627 PASS, 11 SKIP, 0 FAIL; Vue 228, mock browser 44, auth 6, responsive 18 all PASS. Those receipts are historical, **not** final-head receipts. Previous CI image inventory had `production_deployed=false`, data qualification not asserted, missing published registry digest; CI smoke is not a release. After newest PR52 parent, independently rerun and append actual checks/artifacts to PR54; report failures without bypass.

Human/production login, phone, natural 2 trading days, settled 34 prices and cloud zero-growth remain independently PENDING. Source/license/quantity units/PIT/OOS/calibration **UNKNOWN**, `actionable=false`, `not_calibrated`, no automatic trading. Local Codex receives fixed SHA only after remote SHA/tree/readback and CI review. Local Windows full pytest remains a separate required acceptance (especially corrected test-only OCR spawn contract).

Hub report NOT_SENT; Owner's Windows Hub CLI unavailable with C2C tunnel down. No credentials or private data requested or accessed.
