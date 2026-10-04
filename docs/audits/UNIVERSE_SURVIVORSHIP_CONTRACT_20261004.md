# Historical universe and survivorship-bias audit — 2026-10-04

Branch: `codex/post-release-indicator-audit-20261004`
Stage base: `2b9578c5a0dc6fb4c0b13515185ef8754633a6ee`
Production remains frozen at `efc0898dd13d386b8b4d91854323e36ceffa0630`.

This stage addresses a credibility boundary, not a provider purchase or historical-universe reconstruction project.

## Evidence found

The current Instrument model stores only the present `enabled` flag plus metadata. There is no persisted historical universe-membership interval or delist/effective-membership history. Tushare catalog discovery may attach `list_date`, but the catalog endpoint is queried with live status and the repository's own `build_etf_universe.py` already documents that its pool is a LIVE-fund pool and is **not survivorship-bias-free**.

Therefore the system does not have enough evidence to reconstruct a point-in-time historical investable universe. This stage deliberately does not invent delisted constituents or infer membership from later data.

## Shared universe contract

Factor/global research and transaction backtest now publish the same explicit contract:

`research-universe-v1-current-enabled`

It records:
- current-enabled selection semantics;
- exact current instrument codes;
- listing-date evidence and coverage;
- `historical_membership_available=false`;
- `delist_history_available=false`;
- `survivorship_bias_controlled=false`;
- `qualification=UNKNOWN`;
- limitations explaining that known list dates prevent pre-listing observations but do not solve survivorship bias.

The contract is content-addressed in factor/global/backtest/crosscheck metadata.

## Listing-date filtering

When catalog metadata contains a valid `list_date`, factor research and transaction backtest remove bars before the listing date. The removed-row count is preserved in factor research-basis evidence.

If listing date is unavailable, historical bars are not guessed or truncated. The report instead shows incomplete listing-date coverage.

This fixes pre-listing contamination without pretending that current-enabled membership is historical membership.

## Factor/global research

Factor panels carry both:
- canonical research price-basis evidence; and
- the explicit universe contract.

The contract is explicitly reattached after pandas enrichment transformations.

Global-model research refuses to run if its factor panel lacks an explicit universe contract. It records the complete contract plus a stable hash.

## Transaction backtest

The transaction backtest filters known pre-listing bars before the existing raw-price/execution-basis checks. Its report embeds the current-enabled universe contract plus:
- execution-included codes;
- execution exclusion count.

This remains a current-survivor research universe. Backtest reports are still `qualification=UNKNOWN` and revision PIT remains unqualified.

## Independent crosscheck

Crosscheck does not rebuild its own universe from current `enabled` flags. It replays the primary report's codes and requires the primary universe-contract version to be present. It stores the primary universe-contract hash with the replay receipt.

This avoids changing the primary historical sample merely because current enablement changed after the backtest.

## Version isolation

Because known listing dates can change research/backtest sample inclusion and universe semantics are now part of the evidence contract:

- factor analysis: `factor-analysis-v0.2.2-universe-contract`
- global-model research: `global-model-research-v0.2.2-universe-contract`
- transaction backtest: `rotation-v0.5.4-universe-contract`

Formal indicator/feature/forecast identities are unchanged.

## What this stage does not solve

A survivorship-bias-free historical ETF/LOF universe would require an independently sourced and persisted membership/lifecycle dataset, including delisted funds and effective dates. That is a separate human/resource/provider decision and is not inferred or silently activated here.

Until such evidence exists:
- factor/global cross-sectional results are diagnostics on a current-survivor pool;
- transaction backtests are not historical investable-universe proofs;
- no strategy/model/data qualification can be promoted from these results.


## Crosscheck listing-date symmetry

Remote static review found one replay asymmetry before local handoff: primary backtest hashes are computed after known pre-listing rows are removed, while crosscheck initially reconstructed all raw rows. A valid primary report with pre-listing fixture/history could therefore be misreported as `primary_inputs_changed`.

Crosscheck now filters replay bars using the **listing_dates frozen in the primary universe contract** before hashing or replay. It deliberately does not re-read current Instrument metadata for this decision. A regression proves that primary listing evidence controls replay filtering and that codes without frozen listing evidence are left untouched.
