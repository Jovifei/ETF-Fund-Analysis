# Local producer admission and reconciliation

Execution policy: `private-research-execution-v1`. This changes execution scope,
not indicator formulas, forecast values, data normalization or calibration.
This is a runtime contract, not a grant of upstream rights. No
provider name, installed library, personal-use claim or owner consent establishes
the upstream permission or observed units. Keep credentials in the existing
private credential store; the following configuration contains no credentials.

`config/live.json` must exist and contain a nonempty, unique `universe` of ETF
codes. Real execution requires `--expected-sha <full clean approved SHA>`. A
changed code/config identity, absent local ownership marker or missing existing
dedicated `research.sqlite3` stops before collection. Mock execution cannot upload.

## Explicit owner-private execution

Jovi's authorized existing personal research route may use `--private-research`
with only the existing `public_composite` or `akshare` provider. This permits the
operation while keeping `admitted=false`, upstream `license_status=UNKNOWN`,
`source_qualification=UNKNOWN`, and `source_timestamp_quality=UNKNOWN`. This is
distinct from an upstream license or a certified dataset, and does not enable
commercial/public redistribution or other paid sources. Explicit DENIED,
REVOKED, EXPIRED or dated-expired evidence still refuses execution. The private
compute settings copy disables Tushare/FTShare fallback; credentials/configs are
not changed. Its TaskExecutionPolicy also disables runtime-provider resolution,
so a stored runtime token cannot restore a paid fallback; operational task/audit
history remains enabled. Normal executions keep the existing default resolution.
The Windows registration helper has an optional `-PrivateResearch`
switch, default false, which adds the explicit CLI flag to the pinned task.

The manifest records `usage_scope=owner_private_research`, UNKNOWN source/license
qualification, `research_only=true`, `actionable=false`, `not_calibrated` and the
execution policy version, never private permission documents. Exported forecast
calibration labels are conservatively not_calibrated; stored rows and numeric
outputs are unchanged. Existing ProviderAdapter quality checks still apply:
unknown quantity fields remain null and dependent indicators cannot acquire
qualification through this execution flag. Optional market-context/sector
refresh failures are required=false/unavailable and export explicit empty parts;
core bars/quotes and derived required tasks still reject partial/failure.

AKShare describes public-source local collection for academic research; this
does not establish a separate verified license for each upstream. Its Sina
history documentation and decoder do not establish a uniformly normalized
volume/amount contract; current price-only quarantine remains unchanged.
Sources: [official project overview](https://akshare.akfamily.xyz/introduction.html),
[official ETF interface documentation](https://akshare.akfamily.xyz/data/fund/fund_public.html#fund-etf-hist-sina),
[Sina decoder source](https://github.com/akfamily/akshare/blob/main/akshare/fund/fund_etf_sina.py).

## Optional documented-evidence route

Without that explicit owner scope, embed a `provider_admission` object using `provider-admission-evidence-v1`, with
the exact selected provider and unique interfaces named `daily_bars`, `quotes`,
`sector_snapshots`, `market_context`. Each interface needs:

```json
{
  "name": "daily_bars",
  "valid_until": "2026-12-31T00:00:00+00:00",
  "acquire": {"status": "UNKNOWN", "evidence_type": null, "evidence_ref": null},
  "store": {"status": "UNKNOWN", "evidence_type": null, "evidence_ref": null},
  "display": {"status": "UNKNOWN", "evidence_type": null, "evidence_ref": null},
  "units": {"volume": null, "amount": null, "return": null, "evidence_ref": null},
  "adjustment_basis": {"value": null, "evidence_ref": null},
  "source_timestamp_quality": {"status": "UNKNOWN", "evidence_ref": null}
}
```

Do not change these placeholders to VERIFIED without actual evidence. Permission
requires `status=VERIFIED`, `evidence_type=upstream_terms_or_license` and an
auditable evidence reference (an `owner-approval:` reference is insufficient).
Acquisition and storage are checked separately from display. `--compute-only`
permits collection/calculation with verified acquire/store rights and produces no
display bundle. Display export/upload additionally requires verified display
rights, normalized `volume=shares`, `amount=CNY`, `return=fraction` with evidence,
documented `raw` or `qfq` adjustment, and verified source-time evidence. All four
interfaces must qualify. Expired, absent or incompatible evidence is UNKNOWN.
The existing planning JSON is not automatically imported or upgraded to permission.

## Explicit closed-session research inputs

`--closed-session-research` additionally requires `--private-research` and the
live profile. The registration helper accepts `-ClosedSessionResearch` only
with `-PrivateResearch`. The 16:10 slot requires this explicit input contract;
intraday slots keep the existing strict behavior even when the flag is present.
`--skip-trade-day-check` cannot bypass the helper's independent verified calendar.

`closed-session-input-v1.1.1` accepts only a complete newly fetched Sina quote batch.
The current local day must itself be a verified trading day. After 16:00 the
target is its current session; before 09:00 the target is the previous verified
trading session, searching at most 30 days and rejecting any unknown calendar
decision. 09:00..16:00 has no exception, and weekends are not enabled by this flag.
The capture request cannot cross local midnight; export may cross midnight only
while the independently verified target session still matches the captured one.
It binds the exact universe,
pre-fetch quote ID boundary, actual task run/status/counts and fetch start/end
window. Every new row must have finite positive price, a quality hash, a source
time on that target session within 15:00..16:00, fetched within the current same-day window,
and the exact existing phase-specific degradation: after 16:00 same-session
materials require `quote source timestamp is stale`; before 09:00 the independently
verified previous-session materials require the real MarketService classification
`quote source date is not today`. The two reasons are not interchangeable, and
the target-session/source-time checks still reject genuinely older or future data.
The manifest records the accepted original reason without changing the stored
quote's realtime/verification/status or TaskRun partial result. Missing,
extra/duplicate, old-session, future, non-Sina/Mock, invalid-price, other-degraded,
unverified-calendar or cross-midnight inputs refuse. SQLite naive dates follow
the existing snapshot-contract settings.timezone convention, never a guessed UTC.

Acceptance is an in-process typed result plus bound evidence hash, not a Boolean
read from external JSON. Its private provenance binds the canonical owned SQLite
file identity, exact universe, captured row IDs and original fetch boundaries.
Export revalidates the actual task and all captured quote columns in its own
transaction, then uses instrument_detail's exact source-time/ID selector and
checks its exported quote DTO. Another DB, a changed payload/session/scope or a
different winning quote refuses; a new engine on the same SQLite file is valid.
No database path or credentials enter the public manifest.
Original QuoteSnapshot flags/reason and TaskRun status
remain false/stale/partial. Only local research may continue; nothing is marked
realtime, actionable or calibrated. The signed manifest's `input_observation`
records the contract, `closed_session_nonrealtime`, source session/time range,
batch hash/count and non-realtime UNKNOWN qualification, with no account data.
This changes orchestration input acceptance, not formulas or strategy thresholds.

## Bounded public-history recovery

Private compute explicitly passes `retry_history_once=true` for daily history.
Normal callers retain the old default false and old result shape. Only the
existing public_composite/akshare scope with an actual CompositeProvider and a
current failed ProviderError/deadline trace may repeat a per-code fetch, at most
once for the identical code/date range, when its selected material is not the
existing complete, qualified, same-source batch. An explicit permission,
credentials, rate, endpoint rejection, schema or response-budget error in any
trace forbids retry. Unsupported-only and quantity-unknown-only outcomes do not
retry. A generic failure does not prove that an error was transient.

Attempt-one traces are staged through the original provider-audit function
before Composite.last_trace is replaced, and the final attempt uses the existing
audit finally path; they commit with the existing task transaction, not through
a separate durability claim. Opt-in coverage/result metadata records per-code
attempt counts and `daily-batch-v1.0.4-audited-single-retry`; default executions
retain `daily-batch-v1.0.3-audit`. The adapter still selects a whole same-source
batch, never merges fields or substitutes cached success. Existing validation,
unit, date, partial-failure gates and SDK deadlines remain unchanged. A second
partial remains blocked. This is not a whole-market retry loop; the existing
registered task's 20-minute execution limit remains in effect.

Required task partial/failure stops the pipeline. An incomplete required ETF
overview/detail/chart universe cannot export. Outbox bundles and receipts use
unique temporary files, flush/fsync and atomic replacement. Optional hashed
`chart_periods` holds locally derived `1w`/`1mo` charts keyed by ETF and period;
these keep the daily input generation and cutoff and never imply intraday support.

`export_projection_version=local-display-projection-v1` projects board rows and
detail decisions through the same display fields. SR levels, nearest levels,
zone bounds, methods/groups/strength and evidence identity/time/version remain;
large internal structures and raw references are omitted. History contains only
the last confirmed non-provisional/non-forecast record already produced by the
board; no quote is converted into a daily close. Forecast values and all chart
bars are unchanged. The official producer rejects canonical JSON larger than
16 MiB before writing/uploading; it never reduces the universe or truncates bars
to fit. This is a projection/transport budget, not a change to calculations or the
receiver's conservative shared 64 MiB storage contract. Actual 34-code fit must
be measured on the final export, not inferred from this budget or pretty JSON.

Windows task registration previews by default and creates only a new disabled
task with a pinned SHA. It never overwrites a task. OS file locking prevents
concurrent compute and releases ownership on process exit; an old mtime cannot
justify stealing a live lock. Existing installed tasks require deliberate owner
migration and verification; this patch does not register or enable any task.

Reconciliation requires every v2 receipt field and exact manifest/sequence
identity. Missing receipts/empty outbox/consumer observation NOT_RUN cannot yield
overall PASS. Until a scoped normal-page observer is verified, the aggregate
report remains INCOMPLETE (CLI nonzero). This intentionally distinguishes an
executed local report from acceptance of website consumption.

Observed T+1/T+5 dates come from verified market sessions, never the Nth stored
row. Before settlement cutoff they remain PENDING_OUTCOME. Matured returns require
both exact session bars, finite positive prices, no mock source, fetched times
between session settlement and the read cutoff, and explicit same-vintage qfq
evidence (nonempty price basis identity and source `settlement_status=settled`)
bound to both quality hashes. The wall clock cutoff is necessary, not proof of
source settlement. Legacy stored bars lacking this evidence
stay UNKNOWN. This phase does not manufacture that evidence or certify forecasts,
calibration, actionable signals, real trading-day soak or production deployment.
