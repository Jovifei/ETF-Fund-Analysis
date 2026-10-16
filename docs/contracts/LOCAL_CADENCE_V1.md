# Local cadence, recovery and display projection v1.2

One Windows owner invokes `scripts/run_local_compute.py dispatch` every minute
from 13:50 to 16:50 Shanghai. The eight original observation slots remain;
13:55 is added for base preparation. A minute with no due job performs no
collection. `StartWhenAvailable` is best effort; Windows can delay a missed
start. Timeliness is measured from planned slot to actual accepted receipt,
not inferred from registration ([Microsoft documentation](https://learn.microsoft.com/en-us/windows/win32/taskschd/tasksettings-startwhenavailable)).

`state/schedule.sqlite3` is local control evidence, separate from research and
account databases. An OS file lock owns execution; SQLite transactions only
claim or record work. The ledger retains failed and interrupted attempts,
TaskRun identities, actual planned/start/finish times, source/config/scope,
immutable package names and validated receipts. A durable UTC watermark blocks
clock rollback. A newer due slot supersedes older unstarted work; yesterday's
observations are never reconstructed as current successful slots.

Ledger v1.1 uses control schema 2 and retains the public manifest in a bounded
64KiB immutable record. It records EXPORTING intent before atomic file writing;
after a crash the exact manifest/body may be recovered, otherwise the attempt
is explicitly QUARANTINED. Unrelated outbox files are never adopted or deleted.
Supersession ends the old slot, attempt and pending upload job together.

Compute retry is bounded to two attempts with a 60-second cooldown. Exported
packages survive process/network failures. Initial POST plus two transport
retries send the identical package with fresh authentication nonces. Package
expiry, source/config/scope changes, current-session catch-up window (20
minutes), and fast-observation age (8 minutes) gate replay. Exhaustion records
FAILED_DELIVERY; it does not issue a new sequence just to resend content.
The current complete config-file bytes, provider, profile, explicit research
scope, canonical database identity and upload destination form a separate
execution hash. Before each replay the current config and provider admission
are checked again, including explicit withdrawal or expiry. This execution
identity does not replace the strategy config hash used by the receiver.

Managed packages bind `local-execution-lineage-v1` in the signed manifest:
actual full/fast mode, execution hash, config-file hash, base-input hash and
captured-quote-batch hash. The ledger's execution-context job must match that
manifest exactly. Private configuration/path contents are never included.

## Input and field dependency contract

| Output | Input and freshness |
| --- | --- |
| Quote / provisional OHLCV | Newly captured target batch, original provider timestamp/quality, existing 8-minute guard |
| Settled indicators / forecasts | Original settled-session inputs, source/config/version and exact raw/history/feature lineage; original as-of retained |
| Signal / decision board / structural snapshots | Recomputed from validated settled base plus captured current quotes; original all-enabled research background retained |
| Multi-period charts | Built locally for the same actual board/read-as-of; no server-side research calculation |
| Optional sector / market-context corroboration | Not refreshed in fast mode: explicitly unavailable, including nested overview/detail fields and digest |

Base fingerprints include canonical SQLite identity, provider, code/config,
34-target scope, all-enabled background, validated settled session, complete
history/revisions/quality, feature input lineage and successful scoped base
TaskRuns. No formula, prediction labels, thresholds or calibration changes.
The existing 15:15 cutoff invalidates the previous base; it is not independent
proof that today's provider data is settled. Required failures remain failures.
The existing typed non-realtime closed-session exception stays limited to its
previously approved windows and never promotes raw collector quality.

Projection v1.2 suppresses skipped optional evidence at its exact consumer
paths before computing content hashes. Grades are retained because the existing
classification uses quotes/technical indicators, not the appended sector
corroboration. Forecast as-of, board snapshot and input identities are retained.
UNKNOWN / actionable=false / not_calibrated remain mandatory.

## Rollout and acceptance

Preview `migrate_local_cadence_task.ps1` with exact old/new source identities.
Apply requires a fresh verified canonical SQLite backup and creates an
immutable UTF-16 task XML backup. It updates the existing owned action and
triggers, preserves its principal and unrelated settings, and restores its
definition if validation fails. Do not run the legacy and minute controllers
in parallel. Do not restart/log out the computer or change credentials.

`observe_local_cadence.py before` at 13:50 captures a read-only baseline;
`after` at 16:35 compares all 14 research tables' exact counts, INSERT, UPDATE,
DELETE and bytes, database/statistics identity and runtime roles. Missing
metrics, a reset/restart or an incomplete window is not zero-growth PASS.
PostgreSQL's explicit null stats_reset is retained as an identity value, while
a missing field or changed reset identity is UNKNOWN.

Two distinct verified trading days with the same release identities are needed.
Fast delivery target is 120 seconds, full preparation/settlement 600 seconds.
Provider failure or an unmet target is recorded; no market gate is relaxed.
Stability verifier v2 checks the entire required stage set, unique TaskRun IDs,
actual mode (including full fallback), successful upload and exact manifest /
receipt / execution lineage. Nine distinct, increasing generations are needed;
one quote-only job or one receipt copied across slots cannot pass. Older weak
v1 reports cannot qualify the new release.
Natural Windows event-history evidence, authenticated browser consumption,
phone acceptance and investment-strategy qualification remain separate from
accepted delivery and the two endpoint runtime captures.
