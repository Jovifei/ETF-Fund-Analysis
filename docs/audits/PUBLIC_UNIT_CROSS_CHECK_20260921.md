# Public unit cross-check — 2026-09-21

## Scope

Read-only local probes of the existing AKShare dependency. No database, runtime
configuration, credential, or production state was changed by this probe.

## Source contracts

- AKShare `fund_etf_hist_sina` documents `volume` as `手` (100-share lots).
- AKShare `stock_zh_a_hist_tx` documents its returned `volume` as shares and
  `amount` as CNY after adapter normalization.
- The application binds both contracts to fixed endpoint/version labels and
  still requires same-day independent observations before certification.

References:

- https://akshare.akfamily.xyz/data/fund/fund_public.html
- https://github.com/akfamily/akshare/blob/main/akshare/stock_feature/stock_hist_tx.py

## Observed result

For `510300.SH`, `512480.SH`, `515880.SH`, and `159562.SZ`, the current
AKShare runtime returned overlapping 2026-09-01 through 2026-09-18 rows from
Sina and Tencent. The compared rows had identical closes; after converting
Sina volume from lots to shares, volume and amount ratios stayed within the
numeric precision of the two public responses. A bounded 35-symbol coverage
probe returned 31 symbols on the first attempt; the four transient connection
timeouts all returned 14 valid rows on one immediate retry.

This is evidence for the adapter contract and source reachability, not a claim
that all historical dates are certified. Production certification remains
bound to the exact stored bar hash, same-day pair, and the requested evidence
range.
