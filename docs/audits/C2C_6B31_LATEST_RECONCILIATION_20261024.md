# c2c_6b31 — latest-PR reconciliation review (2026-10-24)

Status: SOURCE_RECONCILED / CI_PENDING. No merge or deployment. Repository reads/writes used the installed GitHub plugin only, no C2C workspace/local tunnel. All input data and git refs were independently read.

## Concurrent upstream changes resolved (do not overwrite Owner's code)

A new isolated branch was originally created from PR52 `ea6e965ae5a8e49f204e8dcf5bb065072ffd4fdc`. Its documented failing browser reproduction is unchanged and remains archived at `docs/audits/C2C_6B31_RED_INTEGRATION_20261024.md`, backed by `workspace-ci` `40051857466` (**Vue 228 PASS, mock Chromium 44 PASS, authenticated 5 PASS / 1 FAIL at missing `market-context-status`**).

During review, original PRs moved independently:
- PR51 latest snapshot `ba86baf9f10a43531e09538622cad825afbcc89d` (tree `7b34ecedbd4d63f4483f92930eed9c64288645ed`); its post-f6 revision includes a fail-closed 2-line receiver guard when `previous` exists but `latest` is absent, plus regression, strengthened authenticated browser test and responsive viewport checks.
- PR52 latest snapshot `82916e5acc9d036606b1bcd84bc0a9d17f9c690f` (tree `78fb1076de250382ef44bd08d923a5f83226ccf5`), merge parents `ea6e965a` and `ba86baf9`. It already contains all those recent PR51 changes along with document consolidation.
- PR53 final `fdaf5426585d64800dbff60656797cd75306f19e` (tree `6c2450558b2f862e4fc5fbd6929a1999c6ae7d33`), still separate. Its production fixes up through f89 already appear in PR52 ancestry; final fdaf contains a test-only rolling fixture.

Our original integration candidate `fac4d2b0d9aea12b5869b5b27d5b479ae74f5a20` implemented the exact missing read_contract and noninteractive index card test, but the newer Owner-authored `frontend/e2e-auth/local-display-consumption.spec.ts` (blob `18b5ddce589f1faab27d74e721ef98e9d937e0f3`) is stronger: complete generation/source/refreshed/generated/read timestamps; explicit carried-forward, stale and historical labeling; absent action/buttons and index/minute calls; pinned instrument detail and strict workspace POST prohibition. **Adopt it verbatim** in the final integrated tree. Do not replace it with our shorter earlier fixture.

Likewise preserve the newer PR51 rolling peak instrumentation in `test_display_cache_rolling.py`: `watch_atomic_peak` wraps `os.replace` and checks transient `domain.used_bytes()+domain.held_bytes<=domain.max_bytes`; 8KiB synthetic pointer headroom, 1024B chunk hold and max_generations=3 remain. Only add outstanding fdaf invariants: exact retained count, zero held bytes when complete, prev/second generation protection and bounded used+held. Blob `928b56e802b2fb559bc08368254e20274097f91b` retains the atomic watcher. `SyncDomain`, `LocalDisplayStore` production logic, all quotas and thresholds remain unchanged.

## Merge strategy and verification contract

The final isolated commit uses a **two-parent Git merge** with first parent this task's own `fac4d2b0` history and second parent the latest PR52 `82916e5a`. Its tree is deliberately based on **exact PR52 latest tree**, overlaying only our stronger rolling-test assertions and the two new c2c_6b31 audit/handoff documents. This retains Owner's newest backend guard, tests, controlled browser improvements, responsive checks, docs, and Vite 7.3.7, and contains the earlier explicit RED receipt in ancestry. No source cherry-pick can silently replace latest Owner test/code.

Full CI gates on **new merged SHA** must be independently checked:
- `ci`: whole Python pytest/compileall/node/secret scan/Alembic/Shell/Compose/container build+smoke;
- `workspace-ci`: `npm audit --audit-level=high`, backend contracts, TypeScript, complete Vue/Vitest, build, mock/real-auth controlled/viewport Chromium;
- `audit-platforms` and `postdeploy-ci` (CI tests, not deployment).
Never re-label PR51/52 results as merged-SHA PASS. Record any fail/skips and absolute new run IDs; no bypass, no reduce test counts, no timeout relaxation.

Readback targets: `main` remains `1a4b6652f49c412145d12812fa02820ba0a80991`; PR51/52/53 branches unmodified by this task. This branch remains Draft and no deploy. Provider permission/license/PIT/OOS/calibration and real user/phone/two-trading-day acceptance stay PENDING/UNKNOWN; `actionable=false`, `not_calibrated`.
