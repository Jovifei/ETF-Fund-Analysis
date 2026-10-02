# S8-F0 Source Evidence Matrix v2 — 2026-10-02

Status: UNKNOWN / EVIDENCE_COLLECTION

This matrix separates repository code inventory from upstream capability. Capability does not imply project permission or qualification.

| Source | Official reference | Access date | Repository adapter | 5m/15m scope | Volume evidence | Amount evidence | Time/PIT evidence | License/Fee | Status |
|---|---|---|---|---|---|---|---|---|---|
| Tushare Pro | https://tushare.pro/document/2 | 2026-10-02 | Pending inventory | Official minute capability requires scoped verification | Pending endpoint dictionary | Pending endpoint dictionary | Pending | Permission/cost must be verified | UNKNOWN |
| AKShare | https://akshare.akfamily.xyz/ | 2026-10-02 | Pending inventory | Interface capability separate from upstream source | Pending upstream verification | Pending upstream verification | Pending | Package license does not prove upstream rights | UNKNOWN |
| Sina/other sources | Pending official source review | 2026-10-02 | Pending inventory | Pending | Pending | Pending | Pending | Pending | UNKNOWN |
| Existing repository adapters | Pending code inventory | 2026-10-02 | Pending | Pending | Pending | Pending | Pending | Pending | UNKNOWN |

## Frozen probe contract

- ETF scope: 510300.SH plus one second ETF selected before execution.
- Window: 20 trading days connectivity/evidence check only.
- Frequencies: native 5m, native 15m, and causal 5m->15m if supported.
- Maximum 20 requests/source.
- Timeout 10 seconds/request.
- Stop on permission failure or repeated provider failure.

## Required evidence

Each source must bind:
- endpoint/interface
- official documentation URL
- access date
- access condition
- field dictionary
- volume unit
- amount unit
- source timestamp versus fetch timestamp
- history/PIT/adjustment contract
- license/storage/repeat access limits
- bounded probe receipt

## Conclusion policy

FEASIBLE requires evidence.
CONDITIONAL requires identified unresolved conditions.
NOT_FEASIBLE_WITHIN_SCOPE requires scoped failure evidence.
UNKNOWN remains valid when evidence is incomplete.

No procurement, credentials, production writes, schema changes, or qualification promotion.
