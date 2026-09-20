# Production deployment receipt — v1.0.8 / evidence closure

Date: 2026-09-21 (Asia/Shanghai)

## Release identity

- Runtime source before this documentation-only receipt: `0038c43`.
- Production image: `etf-workspace:v1.0.8-public-rounding-0038c43`.
- Image ID: `sha256:aa543e45247f26f85757a21d8932f0dc40e09f9c938a96b61746fe605aadad1c`.
- Data contract: `cn-fund-shares-cny-v1.0.8-public-rounding`.
- Alembic: `e609200001 (head)`.

## Deployment checks

- API, worker, and single scheduler are healthy on the v1.0.8 image.
- Public `/api/health` returns production, `public_composite`, version `1.0.8`, and auth enabled.
- Application mounts are limited to `/app/reports` and `/app/backups`; no source-code mount is present.
- Main application routes return 200; compatibility routes return their expected 307 redirects.
- Final pre-deploy backup: `/opt/china-fund-decision/backups/fund_decision_pre_0038c43_20260921_031255.dump`.
- Backup SHA-256: `38142a8fcc1b0a811cb9004ebd31254cc5a0d86e3864d322a65aeae57607bf8d`.
- Backup permission: `600`; `pg_restore --list` reports 401 TOC entries.

## Evidence result

The audited `certify_units` run completed with 35 instruments, no task failures,
and 140 certified rows out of 148 stored evidence rows. The eight remaining
rows are `daily_bar_quantity_missing` for price-only history:

`512000.SH`, `512200.SH`, `512480.SH`, `512800.SH`, `515220.SH`,
`515880.SH`, and `588200.SH` (the last has two uncovered rows).

No row is marked certified without stored quantity values, same-day independent
source evidence, and the current daily-bar quality binding. Realtime quote,
PIT/OOS, forecast calibration, and actionable gates remain unchanged.
