# Cadence recovery: fixed-source review gate

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
