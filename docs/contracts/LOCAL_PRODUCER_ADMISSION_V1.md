# Local producer admission and reconciliation

This is a fail-closed runtime contract, not a grant of upstream rights. No
provider name, installed library, personal-use claim or owner consent establishes
the upstream permission or observed units. Keep credentials in the existing
private credential store; the following configuration contains no credentials.

`config/live.json` must exist and contain a nonempty, unique `universe` of ETF
codes. Real execution requires `--expected-sha <full clean approved SHA>`. A
changed code/config identity, absent local ownership marker or missing existing
dedicated `research.sqlite3` stops before collection. Mock execution cannot upload.

Embed a `provider_admission` object using `provider-admission-evidence-v1`, with
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

Required task partial/failure stops the pipeline. An incomplete required ETF
overview/detail/chart universe cannot export. Outbox bundles and receipts use
unique temporary files, flush/fsync and atomic replacement. Optional hashed
`chart_periods` holds locally derived `1w`/`1mo` charts keyed by ETF and period;
these keep the daily input generation and cutoff and never imply intraday support.

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
