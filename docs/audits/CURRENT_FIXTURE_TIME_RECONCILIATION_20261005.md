# Current fixture time reconciliation — 2026-10-05

Branch: `codex/post-release-indicator-audit-20261004`.
Base: `655614c89d14d121880d8f9cfb9823e395352c7e`.

## Intake

The current source retains `47794a2` shared-fixture repairs and `655614c` trade-activity execution gates. Local acceptance branch `30b7c68` adds reception records, not a newer implementation. Its receipt and exact CI run [37217228662](https://github.com/Jovifei/ETF-Fund-Analysis/actions/runs/37217228662) both identify the remaining SignalCenter time/order issue. Workspace/platform workflows succeeded; full CI failed in three SignalCenter cases.

An earlier independently reviewed candidate based on `8cc7a69` reached 1725 passed / 11 skipped, but that result is historical and **does not validate this newer base**. The candidate was preserved rather than overwriting the concurrent upstream fixes.

## Minimal correction

Only six fixture lines change:

- Synthetic current indicators/signals are stamped using aware application-market time, after bootstrap, rather than naive host time minus an arbitrary number of minutes.
- The recent news fixture uses the same timezone convention.
- The board fixture is generated at the observed fixture time, not one minute into the future.

A host in UTC or America/Los_Angeles can be on another calendar day from Asia/Shanghai. Treating its naive `now()` as market time can make a positive fixture expired, older than bootstrap or a different date. The production compatibility/latest ordering rules are retained, as are all original assertions.

No application, strategy, formula, signal threshold, qualification, deployment or data-source change is included in this patch.

## Verification

Fresh baseline RED, focused, full-suite and independent-review results will be appended after their actual completion. The ephemeral prior environment was replaced; dependency/test results are being recreated rather than inherited.

## Next bounded audit

Separately reproduce current-decision and SignalCenter acceptance of future board snapshots and SignalCenter's direct consumption of legacy raw board grades. Keep these runtime changes in a subsequent reviewed stage. Classification evidence identity remains a further audit item.

Data qualification remains UNKNOWN; actionable=false and calibration_status=not_calibrated. No deployment or investment execution is performed by this fixture stage.

### Recreated baseline and static review

- Fresh baseline SignalCenter on exact `655614c`: 3 failed / 8 passed, 21.22 seconds. Failures match the hosted CI: take-profit empty, sector ranking, and current-front production signal provenance.
- Independent static review PASS: all 63 AST assertions unchanged; application code unchanged; diff check passes. Frozen candidate file SHA-256: `33fcc74506dc132c990cdad165af40094067a6b559cad3395265abcaf1084ee2`.
- Python application compile, legacy app JavaScript syntax, committed-secret scan and progress-view consistency checks passed.

### Frozen six-line candidate result

Fresh complete backend run on `655614c` plus the six-line fixture change: **1,736 collected, 1,725 passed, 11 skipped, 0 failures/errors**, 1029.739 seconds. JUnit SHA-256: `1a3dc8c627c7a24b972e2b3748956a35d6561c3e73cbbbf1f67ff28b80a4e8bf`. The skips remain platform/optional-engine/archive cases; no skip or assertion was added by this patch.

The expanded deliberately ordered subset (SignalCenter → history → board → temporal contracts) produced **73 passed / 3 failed** out of 76, 415.316 seconds. These additional failures are preserved, not called a pass:

- A single-instrument board test assumes whole-database `refresh_all.created == 1` even after other modules add refreshable instruments.
- A provisional-input test assumes the shared table starts empty.
- The missing-indicator scenario deletes an arbitrary first snapshot even when another snapshot for that instrument remains.

These are scheduled for a separate fixture-isolation stage, retaining the original assertions. An initial isolated candidate passed the three affected cases together with both preceding modules (34 tests), but is not included in the frozen six-line candidate or represented as a final reviewed fix.

Exact committed hosted CI remains pending after publication. Full-suite success in its normal order does not imply order independence, runtime board-read safety, live data qualification or deployment readiness.
