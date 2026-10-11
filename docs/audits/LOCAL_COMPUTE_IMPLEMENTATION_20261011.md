# Local implementation and controlled shadow receipt — 2026-10-11

## Identity and scope

Owner explicitly authorized local implementation with webpage GPT review. Implementation branch `codex/local-execution-20261011`, [Draft PR45](https://github.com/Jovifei/ETF-Fund-Analysis/pull/45), based on main `e722ad5d351da05ad01abfb7d5d2d339a6b75773`. Fixed implementation `f514a6ec889d79109df12314947c8e77ed1948be`, tree `ba18dbfe20117afb46469f6b7b0b2b4a4fd150a0`. Documentation-only receipt successors do not replace that tested source identity. Owner checkout and its untracked files/configuration/database remain untouched. No merge, production deployment, live provider request, paid AI, network change, or trading occurred in this stage.

## Delivered work

1. Sector evidence admission rejects wrong source, Mock, future session and future fetched time before latest-row selection. Independent v2 observation contract blocks legacy/incompatible summaries without changing canonical grades.
2. Disabled `shadow-display-v1` exports same-generation board/daily charts/market references to bounded content-addressed storage. Atomic latest publication, protected previous, managed byte-budget GC, expiry/order/source/config gates and public field whitelists are implemented. Cost/holding/user details are excluded.
3. Scoped producer bearer plus domain-separated HMAC binds exact body, key ID, timestamp, nonce, method/path/scope. Durable bounded nonce reservations survive restart. Ordinary database-authenticated sessions read; producer authority is write-only.
4. Dedicated local SQLite jobs use deterministic existing collectors/calculators. Current executable jobs are offline Mock only; explicit verified settled session and420 calendar-day history address warm-up. Full-coverage degraded Mock quote status stays partial; only offline public display transport may continue. Exact clean application checkout is enforced.
5. Windows registrar pins Python/workspace/root/database/code and explicit working directory; calendar-gated slots14:30/14:45/14:50/14:55/15:00/15:15. No GPU or open Codex conversation is required for these formulas.
6. Research helper now distinguishes20d vs5d horizon and actual daily time series vs unknown/member cross-section. Primary-source OSS identities/licenses and reuse mappings are recorded; existing factor code is reused, not copied wholesale or promoted to qualified alpha.

## Actual verification

Environment: Python3.12.10 isolated existing dev environment plus project-declared AKShare dependency, Node24.18.0. No live provider calls during tests.

| Check | Exact source | Result |
|---|---|---|
| Full backend |1595fcf|1825 PASS,23 SKIP,0 FAIL;679.964s|
| Auth/cookie/storage/export focused |178bb43|77 PASS,0 SKIP/FAIL;55.096s|
| Final affected backend |8e0f9e7|120 PASS,0 SKIP/FAIL;60.335s|
| Full backend rerun |f514a6e|1851 PASS,23 SKIP,0 FAIL/ERROR;700.034s|
| Vue tests/typecheck/build |f514a6e|198 PASS/24 files;typecheck/build exit0|
| Static Node regression |f514a6e|27 PASS,0 FAIL/SKIP|
| compileall / Node syntax / PowerShell parser / committed-secret scan |f514a6e|PASS|
| Fixed-source standalone offline collector→compute→export→store |f514a6e|PASS, same_manifest=true,remote_sync=false|
| Actual one-time Windows offline task |8e0f9e7|PASS,result0; owned task removed after completion|
| Actual verified loopback TLS client→receiver |f514a6e|PASS; local test certificate trusted only in client context|
| Identical signed request after receiver restart |f514a6e|HTTP401 PASS; persisted nonce store retained|
| Real DB-login cookie/application read path |targeted tests above|PASS offline; not production account acceptance|
| Chart consumer/public projection |Vue test above|PASS synthetic fixture; not phone/DPR/real-price acceptance|

The f514 CLI generation `a6afde82670ee5a7c4e28951a7724431bdeac674fcd7cffc6558803db51e79d0` carried Mock qualification UNKNOWN; six audited tasks succeeded and refresh_quotes stayed partial/full-coverage degraded. Actual TLS publication used that generation; duplicate generation rejected409, same signed request after process restart rejected401. Only temporary isolated local receivers were used and stopped. Raw synthetic databases/result bundles, temporary TLS keys, task XML and logs stay local and are not published to GitHub.

## Original failures and their disposition

- First full017c313 run:1789 PASS/23 SKIP/1 FAIL. The unchanged composite provider-candidate test lacked AKShare in the isolated environment. Installed the minimal declared dependency; original test passed. Original failed XML retained locally; no assertion or skip reduction.
- Original standalone collector run failed on unsettled Sunday Mock bars; explicit verified settled Mock date resolves it without changing real acquisition dates.
-120-day standalone forecast run failed warm-up; bounded420-day collection resolves it. Full-coverage Mock quotes still retain partial status, rather than relabeling provider quality.
- First actual Windows task wrapper exited1; retained its original XML/log and reran a direct Python action with explicit working directory, which returned0. The initial root cause was not proven, and the failed run is not erased.
- Failure-first regression covers invalid public types, dirty/wrong SHA, storage byte-budget rotation, source admission, research horizon/axis and injected disk/permission/partial-write/pointer/GC failures. Original failures remain in local evidence.

## Webpage review and next stage

Same ordinary fund-project Chat reviewed actual GitHub source. Latest reported conclusion for f514a6e: `SHADOW_STAGE_ACCEPTED_WITH_NON_PRODUCTION_BOUNDARY`; no source writes, no `DEPLOY_RECOMMENDED`. This is an imported remote review conclusion, not a claim of independent execution by that reviewer. Local independently verified the results above.

Next complete stage: controlled shadow operation/qualification, with7–14day observation of sequence/hash/latency/rejection/nonce/storage growth; real scheduled registration/logoff/reboot acceptance; reviewed staging HTTPS; licensed provider integration; same-generation public consumer comparison. These require concrete runtime/resource configuration and remain separate from this disabled implementation. No need to add research features before those gates.

NOT_RUN: public WAN sync, permanent jobs/logoff/reboot, real provider/license/PIT qualification, independent OOS/calibrated strategy, production enabling/canonical cutover, real account production Cookie/R10, physical phone, label collision/DPR2 and genuinely unequal real raw/research price UI acceptance. `UNKNOWN`, `actionable=false`, `not_calibrated` remain mandatory.

See [fixed receiver](../handoffs/LOCAL_COMPUTE_FIXED_RECEIVER_20261011.md), [architecture/recovery contract](../planning/LOCAL_COMPUTE_REMOTE_DISPLAY_20261011.md), [OSS assessment](../planning/OPEN_SOURCE_LOCAL_COMPUTE_ASSESSMENT_20261011.md). Hub service recovered during this stage; a new identity-bound status event b1c0450e-495f-42fa-b339-cbb23113efc8 was accepted at revision1. Earlier failed events remain preserved, not silently retried or claimed sent.

Exact f514 full JUnit SHA256: d0502d44908d4fda929228bdfe20353b6f359ed5521e690fdf2b32459d57b6a1. PR-event workflows on that exact source passed: ci [38137026591](https://github.com/Jovifei/ETF-Fund-Analysis/actions/runs/38137026591), workspace-ci38137026464, audit-platforms38137026568, postdeploy-ci38137026514. The separate push-event full CI38137023388 was still running at this observation; it is not declared passed by the PR result.
