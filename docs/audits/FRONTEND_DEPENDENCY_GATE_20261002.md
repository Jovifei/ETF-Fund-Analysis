# Frontend dependency security gate repair — 2026-10-02

## Scope and baseline

- Repository branch: `codex/remote-stage-s8f0-s2-20261002`.
- Read and cloned baseline: `f9001f5189c1722aef47baaf52454afb04605b9b`.
- Executed in an isolated cloud checkout with Node `24.19.0`, npm `11.9.0`, and Python `3.12.14`. GitHub Actions uses Node 22 and remains a separate verification target.
- Code change: only `frontend/package-lock.json`, `node_modules/brace-expansion`, from `2.1.4` to `2.1.7` (version, resolved tarball and integrity). No manifest, application code, strategy, provider, schema, or production change. Progress documents accompany the lockfile correction as required by the repository contract.
- Dependency path: `@vue/test-utils` → `js-beautify` → `glob` / `editorconfig` → `minimatch` → `brace-expansion`.
- Generated with `npm update brace-expansion --package-lock-only --ignore-scripts --no-audit --prefix frontend`; registry metadata matched the resulting integrity. No `npm audit fix --force`, override, or Vitest major upgrade.

## Reproduction and verification actually executed

| Check | Result |
| --- | --- |
| Before: `npm audit --audit-level=high --json --prefix frontend` | Exit 1; 6 high, 2 moderate, 4 low, 0 critical package findings |
| Clean install: `npm ci --ignore-scripts --no-audit --prefix frontend` | Exit 0; 196 packages installed |
| After: `npm audit --audit-level=high --json --prefix frontend` | Exit 0; 0 high, 0 critical, 2 moderate, 1 low package findings |
| `npm run typecheck --prefix frontend` | Exit 0 |
| `npm run test --prefix frontend` | Exit 0; 18 files, 73 tests passed |
| `npm run build --prefix frontend` | Exit 0 |
| `python -m compileall -q backend/app` | Exit 0 |
| `node --check backend/app/static/app.js` | Exit 0 |
| `node --test` for `decision_board_workbuddy.test.js`, `legacy_route.test.js`, `decision_refresh.test.js` | Exit 0; 27 tests passed |
| `python codex/skills/fund-research/scripts/check_no_secrets.py` | Exit 0; no obvious committed secrets found |

The before/after audit was the failing reproduction and regression gate for this dependency-only repair. Audit counts include affected downstream package entries, not necessarily distinct advisories; the registry metadata was queried separately for each snapshot.

Fixed brace-expansion advisories: [GHSA-qhr7-859c-m2p7](https://github.com/advisories/GHSA-qhr7-859c-m2p7), [GHSA-6j4f-fj2g-mc7p](https://github.com/advisories/GHSA-6j4f-fj2g-mc7p), and [GHSA-q2hr-2g5m-vwhr](https://github.com/advisories/GHSA-q2hr-2g5m-vwhr).

Remaining below-threshold findings are explicit: `vitest` and `@vitest/mocker` moderate [GHSA-82fw-gwwq-j7x9](https://github.com/advisories/GHSA-82fw-gwwq-j7x9), plus `esbuild` low [GHSA-g7r4-m6w7-qqqr](https://github.com/advisories/GHSA-g7r4-m6w7-qqqr). The security gate is green at its existing high threshold; this is not a zero-vulnerability claim.

## Boundaries and next verification

At this receipt's creation, full backend pytest, Playwright browser journeys, migrations, Docker and remote CI for the new commit have not run in this cloud checkout. Full backend test dependencies are not preinstalled, and Docker is unavailable. Check Actions for the exact published commit before treating the complete CI suite as passed. No CI gate was removed or weakened.

The Windows project-hub wrapper and the user's local root-docs synchronization are unavailable from this isolated Linux checkout. No hub CLI success or local-root update is claimed. This receipt and the progress event preserve the handoff; local synchronization is pending.

No stage acceptance percentage, production/source identity, real-data qualification, or deployment gate is advanced by this repair. Existing `UNKNOWN`, `actionable=false`, and pending authenticated/phone acceptance remain unchanged.

## Evidence digests

- `npm-audit-before.json`: SHA-256 `060b1ff9975801d322ae8b091b99fb92d3c551c2c50caa6ec2cbd76130721c6f`
- `npm-audit-after.json`: SHA-256 `9103dc5a5d8368314165ca0a54ca6dc14d3e4503b31bf6ca079a27fafd354bf5`
- `npm-ci.log`: SHA-256 `87d9d20fc6c914a0977b27a6a8e99c6398a28947009e7b8e899796e05b68a349`
- `typecheck.log`: SHA-256 `409317695b29faf9a1c6e4dab9ecf88cc86ad01711ceb281ca5804b6d3a2c571`
- `vitest.log`: SHA-256 `c1ce61a2ce926555befc1a496910e33640df5473d4b4ccb46fd720c3e5bdb08e`
- `build.log`: SHA-256 `9ca750ce9f09d95961f4927f6cfcb8eba16019a11dc8915a3c4333a7a53eb907`
- `browser-js-tests.log`: SHA-256 `874380cb3174a392a4375d10c26bf7c208c6fd436ba7650311140c1a9bb7f0f6`

## Exact published-commit CI outcome — 2026-10-03 Asia/Shanghai

For `67d1a648efa549b3c52743ce5c839ccc527cfec9`, the separate dependency-CI monitor verified these terminal outcomes:

- [workspace-ci 37029499191](https://github.com/Jovifei/ETF-Fund-Analysis/actions/runs/37029499191): SUCCESS, including browser journeys and responsive checks.
- [audit-platforms 37029499188](https://github.com/Jovifei/ETF-Fund-Analysis/actions/runs/37029499188): SUCCESS.
- [ci 37029499272](https://github.com/Jovifei/ETF-Fund-Analysis/actions/runs/37029499272): CANCELLED at the existing 35-minute job limit, last pytest output 29%. No failed assertion or completed JUnit receipt was reported; subsequent compile/static/migration/Docker stages did not execute in that workflow. The prior baseline `f9001f5` exhibited the same timeout pattern.

This is partial CI success plus a full-CI timeout, not a complete CI pass. The existing timeout is being investigated separately; this F0 batch does not alter workflow YAML or weaken tests. No deployment or stage-acceptance gate is advanced.
