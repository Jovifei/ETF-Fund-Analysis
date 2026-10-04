# Current snapshot compatibility and signal provenance audit — 2026-10-04

Branch: `codex/post-release-indicator-audit-20261004`
Stage base: `bf11784a4865c5c960c5f9beaaf7447e461fcc6f`
Production remains frozen at `efc0898dd13d386b8b4d91854323e36ceffa0630`.

This stage distinguishes historical persisted evidence from the current runtime identity. It does not delete, relabel, or migrate old snapshots.

## Confirmed defects

### Current read surfaces selected by time only

Several current-state views selected the latest IndicatorSnapshot / ForecastSnapshot / SignalSnapshot by time but did not require the row to match the current strategy version, feature schema and config hash. DecisionBoard and Workspace detail already had explicit compatibility checks; Dashboard, 14:30, Kline stabilization, SignalGrade, SignalCenter, Portfolio optimization and holdings did not apply the same standard consistently.

The new shared contract is:

`current-snapshot-v2`

The temporally latest persisted row is selected first. If it is incompatible, current consumers expose it as unavailable plus explicit issues. They do **not** silently fall back to an older compatible row.

Historical audit/curve paths may still inspect old versions, but must not present them as current evidence.

### Signal provenance relabelling

SignalService previously selected latest indicator/forecast rows by time, while Preflight could flag an old indicator version/config. The candidate still received the stale row and a newly persisted SignalSnapshot was labelled with the **current** strategy/indicator/forecast versions. A stale input could therefore be wrapped in a current signal identity even though actionability was reduced.

Signal refresh now filters Indicator/Forecast inputs through the current snapshot contract before scoring. If the latest row is incompatible, the current signal records the input as unavailable rather than falling back to an older version.

Every new SignalSnapshot persists `snapshot_inputs` evidence:
- contract version;
- formal forecast horizon contract;
- explicit forecast score horizon weights;
- quote input hash;
- actual indicator input/date/version/schema/config identity, or null;
- actual forecast input/date/model/schema/config identities.

Signal `input_hash` is the hash of that frozen snapshot-input contract plus the current strategy. Current signal readers require:
- strategy / indicator / forecast version matches;
- provenance contract present;
- provenance versions/schema/config match;
- input hash recomputes exactly;
- signal has not expired when a read time is supplied.

Legacy signals without provenance are historical only until normal signal refresh writes a current row.

## Formal forecast horizon drift

The formal forecast contract is configured as `1/3/5/10`. SignalService and Preflight still contained legacy `1/5/20` hard-coding. The 20-day horizon belongs to the separately versioned Research Outlook contract and must not leak back into production signal requirements.

Preflight now requires the configured formal horizons `1/3/5/10`.

Signal scoring preserves its previous effective scoring behavior explicitly: only h1 (0.5) and h5 (0.3) contributed in practice because formal h20 was no longer persisted. The new provenance stores these score weights, while full-calibration completeness is checked against all formal `1/3/5/10` horizons. No new h3/h10 scoring weight is invented in this stage.

SignalV05 forecast-risk adjustment uses the same explicit score-horizon weight contract. Research Outlook remains `1/5/20` and unchanged.

## Current read surfaces

The following current surfaces now reject time-latest incompatible rows without falling back:

- Dashboard: Indicator / Forecast / Signal; issues returned in `snapshot_compatibility`.
- CurrentDecision signal fallback: only current compatible, non-expired SignalSnapshot.
- Holdings forecast overlay: current compatible ForecastSnapshot only.
- ETF 14:30 workbench: current Indicator / Signal / Forecast only; compatibility issues are exposed.
- Kline stabilization: current Indicator and 1-day Forecast; previous indicator comparison uses the existing `previous_same_formula_snapshot` helper.
- SignalGrade: current Indicator and 1-day Forecast only.
- SignalCenter current fronts/sectors: current Indicator and Signal only. Its historical curve remains explicitly `historical_signal_snapshots_legacy_mixed_versions`.
- Portfolio optimization: incompatible indicators are excluded; incompatible signals contribute no score and issues are recorded in the research report.

DecisionBoard and Workspace instrument detail retain their pre-existing stricter compatibility contracts.

## Version isolation

Current signal/read semantics change, so identities advance to:

- strategy/signal: `signal-v0.7.3-snapshot-provenance`
- signal grade: `signal-grade-v0.3.2-current-snapshot`
- signal center: `signal-center-v0.3.1-current-snapshot`
- 14:30 workbench: `etf-1430-workbench-v0.1.4-current-snapshot`

Indicator/feature/forecast formula versions are unchanged. Because indicator/forecast `config_hash` binds the full strategy document, the strategy version change naturally makes prior snapshots current-incompatible until the normal indicator/forecast pipeline recomputes them. Old rows remain historical evidence.

## Qualification boundary

This stage improves software provenance and prevents stale-version consumption. It does not qualify the data, calibration, historical universe, provider rights, or trading actionability.

`REAL_DATA_QUALIFICATION=UNKNOWN`
`actionable=false`
`calibration_status=not_calibrated`
