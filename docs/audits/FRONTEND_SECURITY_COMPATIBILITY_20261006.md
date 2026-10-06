# Frontend security compatibility before publication

## Scope and exact gate

The existing `workspace-ci` gate audits all frontend dependencies at severity high. A fresh lockfile audit reported 3 high, 2 critical, 1 moderate and 1 low findings. The first audit attempt produced no report; only the completed retry is treated as evidence.

Official patched versions establish the bounded update:

- [Vue SSR attribute-name advisory](https://github.com/advisories/GHSA-g2v6-rqmx-r4w6): Vue and its pinned core/compiler/runtime/server-renderer family move from 3.5.21 to 3.5.42.
- [Vitest mocker advisory](https://github.com/advisories/GHSA-82fw-gwwq-j7x9) and [4.1.11 release](https://github.com/vitest-dev/vitest/releases/tag/v4.1.11): Vitest and its paired packages move from 3.2.7 to 4.1.11. This supported version works with the existing Node 22/Vite 7 requirements and no longer depends on tinypool, removing the [worker-options](https://github.com/advisories/GHSA-5gmw-xhrv-c9v3) and [run-options](https://github.com/advisories/GHSA-85c8-ppgw-ccpr) findings. No Vitest 5 upgrade or cross-major override is used.
- [source-map-js advisory](https://github.com/advisories/GHSA-68fv-2mgg-jv7q): the shared transitive lock moves from 1.2.1 to 1.2.2 within all existing parent ranges.

The lock changes only the necessary Vue/Vitest closure and source-map-js. The existing Babel parser is retained because it satisfies the new Vue range. Vite, esbuild, Rollup, PostCSS, plugin-vue, jsdom, test-utils, Playwright, TypeScript, vue-tsc, router, Pinia, KLineCharts and icon dependencies remain unchanged. Product implementation, test assertions, backend source, strategy formulas, qualification, database and migrations are unchanged.

## Fresh isolated validation

- Clean `npm ci --ignore-scripts` passed.
- Full dependency audit: **0 high, 0 critical, 0 moderate; 1 existing esbuild low remains**. The high threshold and all-dependency scope were retained.
- All **23 frontend files / 196 tests passed** under Vitest 4.1.11 without source, test or configuration changes. Vue/TypeScript checking and production build passed.
- Independent lock review verified aligned families, removed tinypool, necessary transitive changes, registry metadata and absence of unrelated upgrades or overrides.
- Browser configuration discovers the original 44 smoke cases. The first isolated-copy attempt lacked a tracked seed configuration and did not start tests. After restoring that configuration, the mock server started, but the installed Chromium aborted with a socket-permission error before any page or assertion. Browser acceptance is **NOT_RUN**: the runner reported 44 launch failures before page/assertion execution; these are not a browser pass or demonstrated application regressions. Authentication and responsive browser execution remain for exact CI; their gates are not skipped or weakened.
- The prior 1,762 backend passes / 11 existing skips and independent chart evidence remain source-bound historical results, not a new backend run. All eight preserved implementation/test/audit files are byte-equal to the reviewed chart candidate.

## Publication and acceptance

The outgoing status documents have been minimized while preserving the complete S0–S9 roadmap topology, 131 task identities/states and 13 historical release gates. Generated views still come from the existing JSON renderer. Personal paths, production account statistics and internal operating history are excluded from the new payload; Git history and business data are unchanged.

Publish from the actual remote parent on the same branch without force, then verify that exact SHA/tree in `ci`, `workspace-ci` and `audit-platforms`. Hosted browser results and screenshots are still required; neither local unit tests nor historical browser evidence substitutes for them. No deployment or real-data qualification is claimed. UNKNOWN, actionable=false and calibration_status=not_calibrated remain intact.
