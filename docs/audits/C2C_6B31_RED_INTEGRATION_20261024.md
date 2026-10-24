# c2c_6b31 — exact-source failing-replay and integration review (2026-10-24)

Task: `c2c_6b31`. Owner explicitly authorized isolated GitHub-only branch implementation, not modification of existing PRs, main, production, credentials, strategy, Provider, accounts, holdings or live data.

## Frozen inputs independently read through GitHub

- `main`: `1a4b6652f49c412145d12812fa02820ba0a80991`
- PR51: `f6d0d332ab8bd27f34cb573b31a141f32cc57bac` (tree `f52c2900e7056e42e83cc8699880f28be03f7522`); latest local-reader, source-time propagation, stronger `watch_atomic_peak` tests, Vite `7.3.7`.
- PR52: `ea6e965ae5a8e49f204e8dcf5bb065072ffd4fdc` (tree `df65b2b6d904ec06ca7649332858dbb71b53da6e`); merge parents PR52 older `9aa1f49` + PR51 `f6d0d332`. This already combines the current PR51 with documentation consolidation and is the **isolated integration branch's direct parent**.
- PR53: `fdaf5426585d64800dbff60656797cd75306f19e` (tree `6c2450558b2f862e4fc5fbd6929a1999c6ae7d33`); PR51/PR52 ancestry includes PR53's earlier `f89b3826`, but not final `fdaf542` fixture change.

No automatic git merge/cherry-pick of full PR53: its production change is already ancestral, while its final fixture overlaps PR51's stronger atomic-peak test. Preserve the latter; reconcile only missing assertions.

## Actual RED — BEFORE modifying the branch test

On unchanged PR52 `ea6e965a`, GitHub Actions `workspace-ci` run `40051857466` job `120746057160` **FAIL**, while Vue **228/228** and ordinary isolated Chromium smoke **44/44** passed. Controlled authenticated Chromium: **5 PASS / 1 FAIL** at `frontend/e2e-auth/local-display-consumption.spec.ts:26`:

```text
Locator: getByTestId('market-context-status')
Expected string: "沿用同日"
Received: <element(s) not found>
```

Source contract confirms test fixture omitted `read_contract`, while `Overview.vue` renders `ContextReadStatus` only when `market.data.value?.read_contract` is provided. The actual local Reader/API publishes `local-display-context-read-v1`, so adjust **fixture**, not productive API/UI. Second dormant mismatch: mock-mode test clicks an index-history button that the current local read-only UX rightly removes (it has no published index OHLC). Preserve exact generation and zero-writing assertions, replace click with noninteractive/absent-index-chart assertions.

This is a controlled authenticated test failure, **not proof of failure of a production user's login**. No private credentials or user records inspected.

## Rolling fixture and release security review

PR51's `test_display_cache_rolling.py` retains `watch_atomic_peak()`, measuring `domain.used_bytes() + domain.held_bytes` inside `os.replace`, plus 3-generation forced GC under 8KiB pointer headroom (+1024B chunk receipt hold). This is stronger than a completed-transaction-only used-bytes assertion. Keep it intact; add PR53 final `fdaf` checks for hold released, previous/second cached generation intact, exact max-retained count and total used/held <= cap. Do not replace the file wholesale with PR53; production `SyncDomain`, `LocalDisplayStore` accounting and caps are unchanged.

`frontend/package.json` on PR52 has Vite `7.3.7`, inherited from security-patched PR51. Do not change package versions or lockfile and do not bypass npm audit.

## Verification plan / gates

Post-repair use precise branch SHA: full backend `ci` (pytest/compile/node/Alembic/secrets/Compose/container smoke), `workspace-ci` (npm audit-high, backend contracts, typecheck, Vue unit, production build, Chromium mock/auth/responsive), `audit-platforms` and `postdeploy-ci`. Inspect actual GitHub run IDs, failed/skipped steps and artifacts; do not treat partial or older SHA as PASS.

No automatic merge/deploy. Independent live authenticated website, phone, naturally scheduled two trade days, provider licensing, PIT/OOS and calibration remain separate `PENDING/UNKNOWN`; `actionable=false` / `not_calibrated` unchanged.
