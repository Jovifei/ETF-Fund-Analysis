# Report artifact selection and integrity audit — 2026-10-04

Branch: `codex/post-release-indicator-audit-20261004`
Stage base: `d73bcb38d8a49766a8fb03caef989a23bcb8c22b`
Production remains frozen at `efc0898dd13d386b8b4d91854323e36ceffa0630`.

This stage audits persisted report consumption, not report generation content quality or strategy promotion.

## Confirmed selection inconsistency

Calculation-grade consumers need the **most recently appended system artifact**, not the maximum semantic `as_of_time`. SQLite can strip timezone information from datetime values; the calibration stage already demonstrated that semantic-time ordering can select an older artifact after cross-host writes.

Calibration and backtest crosscheck had already moved toward append identity, while Workspace factor view still selected `factor_effectiveness` by `as_of_time DESC, id DESC`.

A shared contract now owns this selection:

`latest_system_report(db, report_type)`

It:
- filters `user_id IS NULL`;
- orders by monotonic artifact `id DESC`;
- returns one latest global/system artifact.

User-owned reports can never become calibration/crosscheck/factor-system inputs merely because their report type or timestamp matches.

## Bounded authenticated JSON reader

Calculation-grade JSON report readers now share:

`read_system_json_report`

It requires:
- system/global ownership;
- resolved path contained under configured `reports_dir`;
- `.json` file type;
- bounded size (4 MB);
- JSON object payload;
- expected embedded report type;
- exact persisted content-hash match.

This closes path-escape, wrong-type, oversized and tampered-file ambiguity.

Calibration and crosscheck use this reader. Workspace factor view uses it before compatibility checks.

## Validation writer identity

Forecast-validation JSON previously relied on the database row for report type and did not embed its own type. The payload now includes:

`report_type=forecast_validation`

The non-qualifying validation contract advances to:

`forecast-validation-v0.8.1-artifact-bound-research-only`

The calibration-eligible contract allowlist remains empty. This change binds artifact type; it does not improve holdout/PIT/data qualification.

Calibration re-reads and authenticates the validation file **before** returning an existing-candidate `duplicate`. A file tampered after candidate creation therefore reports an integrity/read failure instead of hiding behind idempotence. Approval still independently re-reads and re-hashes the original artifact.

## Workspace factor compatibility

The latest appended factor report is not automatically considered current. Workspace factor read validates:

- persisted content hash and bounded file path;
- current factor-analysis version;
- current feature-schema version;
- research-input contract hash versus ReportArtifact metadata;
- universe-contract hash versus ReportArtifact metadata;
- explicit `qualification=UNKNOWN`;
- presence of a boolean survivorship-bias contract.

States are exposed as:

- `missing`
- `invalid`
- `incompatible`
- `current`

Old/incompatible factor reports remain historical downloadable artifacts but are not exposed as the current diagnostic report.

The read contract deliberately accepts either boolean value for `survivorship_bias_controlled`; future independently sourced historical-universe evidence is not blocked by today's `false` contract as long as the analysis/version/contracts are correspondingly current.

## Tests

Regression coverage proves:
- append order beats reversed wall-clock/as-of ordering;
- a newer user-owned report cannot supersede a system report;
- reports-root path escape is rejected;
- tampered content is rejected;
- wrong embedded report type is rejected;
- user-owned reports are rejected by the system reader;
- Workspace factor selects the latest appended artifact and rejects stale analysis versions;
- a subsequently appended current-compatible factor report becomes current;
- validation artifacts embed their report type;
- tampering after candidate creation is detected before duplicate short-circuiting.

## Qualification boundary

This stage authenticates stored software artifacts. It does not make the underlying validation, factor research, backtest, provider data, historical universe or PIT evidence qualified.

`REAL_DATA_QUALIFICATION=UNKNOWN`
`actionable=false`
`calibration_status=not_calibrated`
