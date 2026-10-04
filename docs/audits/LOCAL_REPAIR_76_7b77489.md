# Local reception of remote core repair — 2026-10-04

Source: 7b7748921cd989c2f8128539aafa31a23e70f1c8, parent ancestry preserves a6c2368. Remote authored actual source; local did not edit business code.

Working root: E:/project/ETF-Fund-Analysis/.local/remote-stage-acceptance, branch codex/local-chart-algorithm-acceptance-20261004.

Executed: pytest test_rsi_contract.py, test_support_resistance.py, test_indicators.py, test_indicator_state.py, test_support_resistance_zones.py. **21 passed / 1 failed**, exit 1. JUnit: E:/Claude_allow/Download/etf-remote-76-first.xml; readable output etf-remote-76-first.txt.

## CHANGES_REQUIRED

1. Existing regression test_support_resistance_method_version_fits_existing_database_column fails. New METHOD_VERSION support-resistance-v5-rich-indicators has 37 characters, both existing persisted method_version columns cap at32. Keep a distinct version <=32; do not alter schema/production merely for the name.
2. New derived SR indicators are not bound into SR cache identity. An offline pure calculation changed actual boll_std2→3 and indicator_version while SupportResistanceService.config_hash stayed identical; enriched Bollinger levels changed. Current read compatibility checks only SR method/config and raw input_hash, not indicator config/version. Bind complete indicator configuration and version into derived cache compatibility and add invalidation regression; preserve source/basis attrs and GET no-write contract.

RSI new up/down/flat frame/scalar contract tests passed. This does not yet prove complete API/persistence/score propagation or wider indicator mathematical correctness. Full regression not run at this incomplete stage. No new candidate deployed; no production/real-provider operations.

Next: remote fixes these findings and continues the authorized modal/forecast/fractal work. Local receives exact new source SHA and validates, then returns GitHub evidence for remote review.
