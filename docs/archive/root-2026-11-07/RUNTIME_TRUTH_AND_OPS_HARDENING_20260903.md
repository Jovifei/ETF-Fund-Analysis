# Runtime truth and operations hardening — 2026-09-03

This change addresses production review findings that do not alter the canonical ETF grade itself but can mislead an operator about freshness or weaken server-local operational safety.

## Dashboard connection/freshness semantics

The decision board keeps the last successfully loaded snapshot visible, but connection state is now separate from snapshot data.

- A fresh snapshot no older than 8 minutes may display `实时快照`.
- A persisted snapshot older than 8 minutes displays `快照已过期` even if its stored build-time freshness was `fresh`.
- A background poll failure displays `连接异常 · 显示最后快照` while preserving the last data for inspection.
- A successful later poll clears the connection error.
- Invalid/future snapshot timestamps fail closed to a warning state.

This follows the common dashboard rule that last-known data and live connectivity must not share one boolean state.

## Low-confidence forecast contract

`conf < 40` already means `忽略 / 基本忽略` in the reference board. The explanatory composite score now follows the same rule:

- `conf < 40`: forecast component is neutral `50`.
- `conf >= 40`: existing forecast score behavior remains.

This does **not** change the canonical five-grade decision. The composite score remains explanatory only.

## Provider smoke semantics

`provider_smoke.py` now applies the same `MarketService._qualify_quote_timestamp()` rule used when `QuoteSnapshot` is persisted.

The quote result distinguishes:

- `provider_realtime`: provider-level realtime flag;
- `verified_realtime`: application-qualified execution-grade realtime count;
- `realtime`: backward-compatible alias of `verified_realtime`;
- `qualification_reasons`: bounded qualification failures.

A provider-level realtime flag alone no longer makes the smoke output claim execution-grade realtime.

## Backup permissions

PostgreSQL backup artifacts may contain account hashes, session hashes, portfolio data, runtime settings, and server-local credentials stored through the application.

Server scripts now:

- use `umask 077`;
- keep `backups/` and `reports/` at mode `0700` during deployment;
- explicitly chmod database dump and checksum files to `0600`.

This mirrors mature PostgreSQL backup tools that default backup artifacts to owner-only access.

## Optional OCR default

The standard production image installs the `market` extra, not PaddleOCR/PaddlePaddle. The production environment example therefore defaults to:

`OCR_MODE=disabled`

Operators may enable `local_paddle` only after installing the OCR runtime and a qualified local model manifest. The OCR adapter still never downloads models implicitly.

## Explicit non-goals

- No canonical grade change.
- No Signal Center coefficient change.
- No provider priority change.
- No automatic order execution.
- No relaxation of timestamp verification.
