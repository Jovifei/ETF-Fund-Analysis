# c2c_6b31 — fixed-SHA integration handoff (2026-10-24)

**Branch:** `codex/c2c-6b31-integrated-20261024`, Draft PR54 targeting `main`. **Status at file creation:** reconciliation implemented; new merged SHA Actions verification pending. The definitive SHA/tree and CI results are read back from GitHub and appended to PR54 after completion, not invented here.

## Exact inputs and ancestry

- `main`: `1a4b6652f49c412145d12812fa02820ba0a80991` (unchanged)
- PR51: `ba86baf9f10a43531e09538622cad825afbcc89d` (newest Owner receiver guard/auth browser checks)
- PR52: `82916e5acc9d036606b1bcd84bc0a9d17f9c690f` / tree `78fb1076de250382ef44bd08d923a5f83226ccf5` (includes PR51 newest + docs + Vite 7.3.7)
- PR53: `fdaf5426585d64800dbff60656797cd75306f19e`; PR52 inherits earlier `f89b382` code, final fdaf fixture assertions integrated without replacing stronger PR51 test
- Our independent RED-history commit: `64e9c5db11229dbb6825aa5ce0b8e3cf3074c433` from earlier PR52 `ea6e965a` (workspace-ci 40051857466: authenticated 5 PASS / 1 FAIL; missing `read_contract`); initial contract-fix candidate: `fac4d2b0d9aea12b5869b5b27d5b479ae74f5a20`.
- Final integration is a two-parent commit with first parent `fac4d2b0` and second parent **newest PR52** `82916e5a`. Its Git tree is built from PR52 newest tree and overlays only our rolling test and new c2c_6b31 audit/handoff docs. This intentionally uses Owner's newer, **stronger** authenticated E2E in preference to our earlier trial fixture.

See [initial RED](../audits/C2C_6B31_RED_INTEGRATION_20261024.md) and [latest-delta reconciliation](../audits/C2C_6B31_LATEST_RECONCILIATION_20261024.md).

## Source behavior / confined modifications

**No production source changes beyond those already integrated in newest PR52.** The PR52 ancestry contains PR51's bounded immutable generation cache, isolated same-origin/local display, actual receiver acceptance history and missing-latest fail-closed guard, close-session daily-bar cache/retry boundaries, Vite 7.3.7 security patch and consolidated docs. PR53's final fdaf adds only fixture budget metadata/held constraints; do not replay fdaf's entire fixture file and discard PR51's `watch_atomic_peak` used+held os.replace peak check.

Our **only test change relative to newest PR52** is `backend/tests/test_display_cache_rolling.py`: exact three-generation count, zero held bytes on completion, current/previous preserved and second cached generation present, with existing 8KiB metadata +1024B chunk hold, and peak `used+held<=cap` untouched. Adopt the latest PR52 complete controlled authenticated E2E (full `read_contract`, timestamp provenance, read-only index/minute guard, generation and zero writes) and responsive checks unchanged. The original E2E RED is preserved as test-first evidence; cannot claim old failed mock was a real-user production login failure.

No edits to any original PR branch, main, production/database, strategy, Provider, account/holding, backups, release or dependency/CI workflow config. No C2C tunnel use. The GitHub connector is the only path used to access/write repository.

## Exact SHA acceptance & gates

Inspect the **final PR54 head and tree**, ensure branch fast-forward and exact GitHub two-parent tree. Then inspect **CI workflows linked to that SHA**:

1. `ci.yml`: full `pytest -q`, Python compile, static JS, security secrets, migrations, shellcheck, Compose, Docker image smoke and source identity;
2. `workspace-ci.yml`: npm audit-high gate, backend contract cases, full Vue/Vitest unit suite, TypeScript, frontend production build, Chromium mock/authenticated/responsive runs;
3. `audit-platforms.yml`: PostgreSQL/Windows bridge; `postdeploy-ci.yml`: independent tests, **not** production deployment.

Only genuine completed SUCCESS for the exact head counts; keep failures/skips visible, no red→green by skipping tests. If any new browser failure, preserve trace and repair only confirmed root cause on *this* branch before new SHA. On final success, append factual GitHub-run receipt in PR54; no need to rewrite this SHA-agnostic committed handoff.

Source/qualification/real operations remain **UNKNOWN / actionable=false / not_calibrated**. Production login, real Provider, 34 settled bars, phone, naturally scheduled two trading days, cloud resource zero growth and human release acceptance are **NOT_RUN/PENDING**. No auto-merge or deploy; local Codex independently receives SHA and verifies without disturbing Owner worktree. Hub report NOT_SENT (local Windows hub unavailable via broken C2C tunnel).
