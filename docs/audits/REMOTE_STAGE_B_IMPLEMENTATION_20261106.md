# Stage B remote audit: same-rule projection and PIT/OOS evidence boundary

Date: 2026-11-06. Scope: independent `codex/stage-b-pit-replay-20261106`
branch, parent `ab8aa2b898fa79f3cb5445646f89443b7ed1cdf7` (Stage A
`c11f563ceb08446f71cb7ccf0c75fb6437417b42`; baseline main
`2dd06627320a47ef20f46e2d02e682a26c5ea040`).

**This is not a strategy release, a licensed PIT dataset, calibrated forecasting,
or production acceptance.** Qualification remains UNKNOWN; actionable=false;
calibration_status=not_calibrated; all trading requires human decision.

## A — Review of actual Stage A changes

1. `strategy_replay_contract.py`: version and family-weight entries were stable,
   but hash omitted indicator windows, forecast, benchmark/regime, theme and
   portfolio caps, full backtest execution policy. V2 hashes every relevant
   configuration section and carries explicit action/target/market/not_replayed
   metadata. A hash is reproducibility identity, not evidence of provenance.
2. `strategy_family_replay_backtest_service.py`: reused family scoring only;
   `rps120=rps60` was an unjustified substitution and daily factor-rotation
   selector did not match the runtime `SignalV05` state machine. V2 computes
   distinct 20/60/120 rankings and shares the runtime formula, allocation,
   labeling and hysteresis functions on **simulated** holdings. It does not
   reconstruct unknown news, forecast, real holdings, quote premia, true
   historical theme membership, PIT universe or intraday signal timeline.
   Therefore report status is `family_action_projection_partial`, never exact
   full strategy replay.
3. `evaluate_pit_evidence`: `qualified=not reasons` risked mistaking timestamp
   validation for rights and completeness. It now reports a separate
   `causal_order_verified`, rejects missing/naive timestamps, nonfinite fill
   price, and always returns `qualified=False` until separate source admission.
4. Shadow market timezone correction is logically appropriate for Shanghai
   session audit. Added target-date visibility filters so the audit cannot
   read forecasts, observed closed bars, signals or indicators from the future
   of the selected 14:30 audit date.
5. Stage A added `test_strategy_family_replay_uses_runtime_family_contract`
   which consumes session-scoped `bootstrapped` database, shared with tests
   that mutate bars/instruments. This enables order-dependent fixtures. V2
   regression builds a deterministic fixed OHLCV slice and injects only this
   research frame while still running the report, status, state and blocked
   execution paths; it no longer relies on shared bootstrap contents. This is
   a root-cause hypothesis to confirm on the full-suite CI receipt, not a
   claimed run of local pytest from this read-only session.

## B — Runtime-family state replay boundaries

- `blended_signal_score` and `raw_signal_target` are now shared by runtime
  and research projection. `SignalV05Service` retains the reference
  `_market_regime`, `_apply_portfolio_constraints`, `_label_state`, and
  `_apply_state_hysteresis` rules. Runtime `SignalSnapshot.evidence_json`
  receives a scoped `strategy_replay_contract` with actual state and weights.
- Daily research output includes per-symbol `state`, `action_kind`
  (entry/probe/reduce/hard_reduce/observe), `target_weight`,
  `first_step_target_weight`, market regime and the `not_replayed` inventory.
  Unqualified modern `theme_l1` is deliberately replaced with the single
  conservative `未分类` bucket before the shared allocator, so future theme
  classifications cannot leak into historical target sizing.
- A fixed-input exact **rule projection** test compares these same functions
  and actions without claiming actual historical signals, forecasts or fills.
  Historical 14:30 features, prediction, news, owner holdings and intraday
  hysteresis state cannot be reconstructed from settled daily bars.
- Original `RotationBacktestV05Service` is still separately labeled
  `factor_rotation_not_equivalent`, not silently relabeled.

## C — Provider and OOS evidence inventory

Current adapter supports official minute fetch on `TushareProvider` only for
30m/60m (and only when permission exists). `MarketProvider` defines 5m/15m
interface but it is unimplemented in that live adapter; the F0 5m/15m probe
is **offline fixture transport**. `BarRecord` does not prove distinct
source publication time or historical retention rights. News adapter records
published_at but this alone does not prove 14:30 historical availability.

`build_1430_freeze_report` records:
- Data coverage, provider/endpoint, 5m/15m OHLCV+amount units,
  bar-end/source publication timestamps, license and authorized retention;
  Declared decision date must appear in the supplied exchange session calendar;
  a pristine holdout shorter than 120 exchange sessions is rejected;
- Shanghai 14:30 cutoff and the first **post-cutoff** executable observation;
- Source record hashes, code SHA and parameter hash, explicit freeze before
  holdout, horizon-aware purge on each walk-forward test window, held-out
  sessions excluded from fold fitting;
- Explicit holdout access log, contamination from tuning, previous-version and
  `510300.SH` comparison marked NOT_RUN when no real PIT evidence.

No real provider access, permission or data was exercised by the remote
read-only workspace connector. **Source/admissibility/rights remain UNKNOWN.**
All caller-declared “verified” metadata still requires independent authentication;
this offline inventory intentionally reports `candidate_seal_ready=false` until
such a verifier exists, even if all caller-supplied booleans are true.
Holdout-driven tuning contaminates the experiment and invalidates the candidate.

## D — Event constraints

`ConstrainedEventExecution` is a research-only, evidence-gated
execution engine. It enforces T+1 acquired-lot tracking, commission/minimum,
slippage, 100-unit-style configurable lot, suspension/tradability, evidenced
historical limit-up/down status, LOF/QDII historical premium with explicit
percent-point units and effective-dated cross-border/fund kind, portfolio and
single-fund cap, point-in-time theme cap and turnover hysteresis. The executable
ledger never trusts the current Instrument kind or theme when reconstructing
an old session; it requires signed-source-equivalent historical row fields
`fund_kind_pit`, `theme_l1_pit` and verification flags or blocks the trade.
Unclassified existing holdings block additional purchases, not de-risking sells.
Unavailable constraints yield blocked-order reason and never default to
unverified fills. A suspended open is not a valuation mark: the ledger uses
last observed positive-volume close or rejects an unpriceable held position. Historical data from `RotationBacktestService` does not
contain all these metadata fields, so its daily-only projection correctly
blocks entries; `trade_count=0` is **not a profitability result**.

Original rotation baseline trades still exist in its own `RotationBacktestV05`
report; they are not evidence of this constraint-qualified replay. Real
previous-version net return, 510300 benchmark excess return, fill/limit rules
and negative PIT leakage comparisons remain NOT_RUN, not silently claimed
from synthetic fixture or factor-rotation PnL.

## E — Shadow and production readiness

`write_1430_shadow_snapshot` requires Shanghai 14:30 source cutoff, fixed
commit/parameter hashes, rejects post-cutoff features/news/quote time and
creates a once-per-trade-day research JSON with exclusive file creation
(no overwrite). `verify_shadow_snapshot` re-hashes its envelope.
No scheduler, provider credentials, production databases or broker are modified.

Still requires at least **20 naturally scheduled trading-day shadow snapshots**,
a signed artifact chain and independent human review. Production remains
unaccepted pending **two complete natural trading days**, **7–14 days**
observation, fast-slot source-to-receiver <=4 minutes, normal login and mobile
check, and actual AI/SMTP deliverability evidence. Existing older acceptance
receipts are not reused as this stage's proof.

## Test and acceptance protocol

Code changes are prepared via GitHub blob/tree/commit route because local C2C
connector has no command-execution or write API. Local commands are NOT_RUN.
Exact-Head CI evidence is recorded separately on the PR; a red or pending CI
does not count as passed. Required:

```bash
pytest -q --junitxml=stage-b-pytest.xml
python -m compileall -q backend/app
node --check backend/app/static/app.js
```

No production, no main merge, no autotrading. Local Codex independently
checks the immutable Head/tree and replays these tests on its own filesystem.
