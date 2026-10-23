# Cadence recovery: fixed-source review gate

## Remote status correction — 2026-10-21 16:40 UTC

[PR #49](https://github.com/Jovifei/ETF-Fund-Analysis/pull/49) was merged at 2026-10-16 14:53:53 UTC. The remotely verified main and cadence branch both point to `3d1ab1696653403cab2f6942495a1abc0e8c5dfb` (tree `bd59fa1acc2ca50e9564e8f40e0109a77e0c86e2`). Exact-SHA completed/success workflow evidence is recorded in [STATUS.md](../../STATUS.md). Statements below that main remains unchanged or final CI is unfinished describe the pre-merge review stage, not the current remote source state.

This correction is read-only source/PR/CI verification, not a new test run, deployment approval, confirmed production rollout, upload recovery, authenticated consumer acceptance, or two-session acceptance. All original failures, interrupted runs, data-preservation requirements and runtime gates below remain intact and require their own current evidence.

## Original review-stage record

Jovi authorized implementation, tests, webpage GPT review, controlled rollout,
then two verified trading-session observations. This document records the
repair contract; it is not a deployment or two-day acceptance receipt.

The original production baseline is source 9fe9fe8, image 93d4e2956d7f and schema
f0e1d2c3b4a5. Owner main and production remain unchanged while this candidate
is being qualified. PR49 is the review bridge.

## Webpage review findings and repairs

| Finding | Actual repair and negative verification |
| --- | --- |
| Runtime config / permission withdrawal could escape strategy-only replay identity | Complete config bytes, provider/profile/research scope, canonical DB and destination form a separate execution hash. Replay reads current configuration and admission again before credentials/HTTP. Revocation with unchanged strategy hash and other runtime changes are rejected. |
| Superseded slots left exported attempts unresolved | Slot, attempt and running upload job terminate together; original packet identity and failures remain. |
| Quote-only jobs could pass two-day acceptance | Verifier v2 requires actual full/fast stage sets, TaskRun identities, matching execution context / manifest / receipt, successful upload, increasing sequences and unique generations. Weak v1 reports cannot qualify. |
| File publication and ledger confirmation had a crash gap | Durable EXPORTING intent precedes atomic packet writing. Exact immutable files are recovered; missing, changed or unqualified artifacts are explicitly quarantined, never silently recomputed or adopted from unrelated outbox files. |
| Fast input lineage only existed in memory | Signed manifests and bounded immutable ledger records bind execution/config-file/base-input/quote-batch hashes. Export rechecks the real base and quote selection. |
| Replayed board age could hide old quotes | Fast replay checks every scoped quote's actual source/fetch time, quality flags, source and overview/detail agreement against the original eight-minute rule. Full closed-session research remains separately gated. |

Additional reproduced failure: SQLite's deferred outer transaction could leave
a committed nested-savepoint board TaskRun after process interruption. Local
full, fast and board-only task transactions now explicitly BEGIN before nested
work. Real TaskService / SQLite interruption regressions preserve rollback.
Unexpected TaskRun identity substitution is a failed attempt, not a false
successful reference.

No indicators, forecast labels, weights, trading permissions, calibration or
market-quality thresholds were relaxed. Source/license remain UNKNOWN;
actionable=false / not_calibrated are retained. Skipped optional corroboration
is unavailable at the exact nested consumer paths before content hashing.

## Verification and release boundaries

The second webpage review found a real producer/consumer mismatch: dispatch
records an `execution_identity` control job, but the v2 assessor did not allow
that job. The release must include a real dispatcher-to-assessor regression,
with missing, duplicate and mismatched identity rejected. The interrupted
7e4daff full run is retained as NOT_COMPLETED, not a passing receipt.

Real f3ab310 full and fast local runs then exported all 34 targets successfully
without uploading. Those runs exposed another actual contract gap: successful
quote TaskRuns contain requested/received/inserted/realtime counters, but no
coverage_complete/completed/execution_scope. A fabricated successful fixture
had hidden the ledger's missing quote coverage. Local capture-bound typed
control evidence now supplements the ledger only after checking the actual
TaskRun, new SQLite rows, exact target scope, capture window, existing quality
rules and actual detail selector. Raw TaskRun JSON and partial/closed-session
qualification remain unchanged. Plain JSON, stale batches and mismatched
scope/run/content cannot assert this control proof.

The f3ab310 full test attempt was interrupted for this required repair and
remains NOT_COMPLETED. Its source-only webpage PASS is not a release approval.
The fast no-upload observations were 143.103 seconds under concurrent full
tests and 127.816 seconds without that load; both miss the 120-second target
and neither proves HTTPS delivery. Read-only ProviderAudit inspection showed
20.6--55.3 seconds waiting for AKShare spot, whose current adapter always marks
quotes non-realtime, followed by 0.10--0.16 seconds for Sina's actual qualified
batch. The webpage review approved only quote-specific deferred calls, keeping
original qualified/degraded selection priorities and all other operations.
Final fixed-source, selection-equivalence and real timing evidence are required.

Morning 6fd50d9 real full preparation/export completed in 219.667 seconds.
All 34 quotes had capture-bound control coverage; the actual quote stage took
0.166 seconds. This is not a measured fast-slot or HTTPS latency PASS. Its
exact CI exposed four failures: two stub tests omitted the now-required SQLite
schema, and CLI source/config preflight ordering violated existing negative
contracts. The stubs now initialize isolated schema; source identity rejects
before reading configuration, and configuration I/O uses a safe ValueError.
Original assertions and the real capture guard remain. Missing/inaccessible
configuration and dirty/mismatched source have explicit regression tests.

An initial diagnostic wrapper lacked the Windows multiprocessing main guard;
its child argument failures and interrupted attempt are retained separately.
The corrected guarded wrapper produced the actual morning full-run receipt.
No production or project-code workaround was used for that harness failure.
The afternoon original 9fe task execution is previous-release evidence only.

Native Windows qualification has now exercised a new disabled, never-run owned
probe: migrate its action/trigger/settings, restore the original definition
from immutable UTF-16 XML, compare Principals/Actions/Triggers/Settings exactly,
then remove only that owned probe. This passed against the 7e4daff migration
script, whose bytes are unchanged by the assessor repair. The real producer
task and its principal remain unchanged. Saved XML and hashes stay private.

- Keep original failed/interrupted logs. The 2a85e36 and a537c89 full-test
  attempts were interrupted for required source revisions, not reported PASS.
- Re-run full backend tests, static checks and exact CI on the final immutable
  source. A prior working-tree focused run is diagnostic evidence only.
- Obtain webpage GPT review of the final source and evidence before switching.
- Native migration preview has been exercised against the actual original
  eight daily trigger boundaries (HH:mm:00); NextRunTime was not a valid basis
  for an HH:mm:20 guard. Failed preview made no task change. Actual backup /
  migration / restoration qualification remains a release operation.
- New consistent local SQLite backup and streamed PostgreSQL backup are
  retained privately with hashes and integrity receipts. The first stream wait
  timed out; the same existing SSH stream was adopted and finished exit 0 with
  gzip integrity PASS. No second dump or server temporary backup was created.
- Two calendar-dependent sessions, actual close-window latency, Windows event
  history, authenticated consumer and phone acceptance are separate. The
  Windows task-history channel is currently disabled; observation tools do not
  invent natural-trigger event proof.
- Hub revision query currently fails WinError10061. A pending observation is
  retained separately; no revision, event or successful send is fabricated.

Release assets preserve private data/config, old stores, exact rollback images,
authentication and network identity. Cloud research collection stays disabled;
only accepted bounded display results are published.
