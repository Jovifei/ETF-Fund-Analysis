# Production deployment receipt — R1 + A-U1–A-U3

Date: 2026-09-23 (Asia/Shanghai)

## Release identity

| Field | Verified value |
| --- | --- |
| Repository / deployed `main` application SHA | `Jovifei/ETF-Fund-Analysis` / `0dbd3fee58a3f5e080aacbcd8eae8d5964aec54f` |
| Application tree | `f8607b3de8decde6065ccc559c5c26b0262b8e6b` |
| CI source and test result | GitHub run `35843677296`, completed/success; workspace `35843677328`, audit-platforms `35843677240`, also success, all on the same SHA |
| CI image artifact | Artifact `10743320341`, SHA-256 `bade66f941ad1f78fea22edb1771e231e344efd2ca800130cd1ae6d24c2aeedc` |
| Compressed Docker image archive | SHA-256 `2dc52927345b9a01498c67e12691827b4076185835d4c23a24b0fbcc38b2c28f` |
| Runtime image | `etf-workspace:production-0dbd3fe`, image ID `sha256:251a0623c694b07525bd398b52f41eecc17ec3d1216912c6d593b704fc8ae81a` |
| OCI labels | revision `0dbd3fee58a3f5e080aacbcd8eae8d5964aec54f`, tree `f8607b3de8decde6065ccc559c5c26b0262b8e6b` |
| Package / API versions | Python and frontend package `1.0.5`; inherited production `APP_VERSION` and public health response `1.0.8` |
| Database migration | `e609200001 (head)`; this application change adds no migration |

The GitHub run built, started, health-checked, and smoke-tested the image before exporting it. The image archive and its SHA-256 sidecar were downloaded to the approved local download directory, the artifact ZIP digest was checked against GitHub's artifact metadata, and the inner image archive checksum was independently checked again on ECS before `docker load`. The generated CI release inventory still reports `registry_image_digest=null` and `production_deployed=false`; the deployment is evidenced here by the actual loaded image ID and running container inspections, not by that pre-deployment manifest.

## Backup and restore rehearsal

- Pre-deployment PostgreSQL backup: `backups/fund_decision_20260923_141523_Q1UTbz.sql.gz` on the production host.
- Backup SHA-256: `f1136db243b7b6913bdaf9bb902b88ab4e94e90f334350dcd88d0cc7a56d742f`.
- `gzip -t` and sidecar `sha256sum -c` passed. Archive and sidecar modes are both `0600`.
- The 1,662,143,471-byte SQL stream was restored into a new PostgreSQL 16 container on an internal network with no published ports, limited CPU/memory, and no external network. The restored copy contained 106 tables and Alembic version `e609200001`.
- Candidate image `alembic upgrade head` and `alembic check` passed on that copy with no new operations. The packaged workspace diagnostic smoke passed for deep links, CSP, static assets, private API authorization, and 404 behavior. Test containers/network were removed after verification; the backup remains.
- No production row was edited by the rehearsal, no user credentials or raw records were copied into this receipt, and no provider or model request was made by the preflight.

## Production switch and post-deploy checks

The new image was loaded from the verified CI artifact. The production Compose project retained its existing PostgreSQL volume, reports and backup mounts, application settings, external network, and container names. The final override changes only the image reference. The prior image remains available for rollback.

- API, worker, and single scheduler are running on the same image ID and carry the `0dbd3fe` source revision label.
- Application mounts are only `/app/reports` and `/app/backups`; there is no source-code bind mount.
- The configured production Compose retained `APP_ENV=production`, database-session auth, `AUTH_ENABLED=true`, `AUTH_COOKIE_SECURE=true`, `MARKET_PROVIDER=public_composite`, `ALLOW_MOCK_FALLBACK=false`, and disabled LLM/analysis.
- Public `/api/health`: `status=ok`, `environment=production`, `provider=public_composite`, auth enabled, configured version `1.0.8`.
- Public root page returned HTTP 200. The deployed `Profile-Cu3lYZkl.js` asset returned HTTP 200 with immutable caching. Unauthenticated `GET /api/workspace/account` returned 401 as expected.
- Production Alembic remains `e609200001`; the new image's migration entrypoint found no schema change. API and worker are healthy; scheduler is running (no healthcheck is configured for this service).
- The first Compose `up --wait` returned non-zero because Compose cannot wait for the scheduler service, whose healthcheck is intentionally disabled. Manual container inspection then verified the scheduler running, and API/worker healthy; no rollback was needed.

### Resource incident and recovery

Before the image-artifact path was added, four production-host image-build attempts ended with exit 137 during frontend typechecking, despite progressively bounded Docker memory and CPU. Kernel timestamps show a UID 10001 Python process was killed at 16:46 and the scheduler container restarted at 16:48; the timing strongly links this to the last build attempt. The API remained healthy, the worker container did not restart, and the scheduler came back. Its following logs contained 23 `ProviderError`-class lines; raw logs were not retained. The final image was delivered as the smoke-tested CI artifact, and the release scheduler is running on the new image. No further production-host compilation was attempted.

An earlier backup attempt stopped before the script body because Windows CRLF changed the Linux shebang to `bash\r`; it did not create a backup or touch the database. All nine shell entrypoints are now pinned to LF in `.gitattributes`, with a regression test.

## Shipped scope and remaining work

R1 evidence binding and A-U1–A-U3 are in the deployed source: profile, password change, access closure, chart indicator selection, and viewport-bounded indicator popover. Account closure disables login and retains records; it is not permanent erasure. Email/SMS/WeChat verification and recovery are unavailable.

Real-data qualification remains **UNKNOWN**. This deployment did not audit production rows, recertify evidence, call market providers, alter certified/hash/raw OHLCV values, or promote actionable status. Forecast calibration, full return series, PIT/OOS, and 14:30 forward validation remain separate gates.

R2–R6 remain open in order: freshness lifecycle; detail empty states/decision explanations; consistent research basis and complete Chanlun drawing; human local Codex connection; authorized real-data review and subsequent release work. The A-U4/A-U5 real contact verification and permanent deletion flows also remain unimplemented.

## Rollback

The previous image is `etf-workspace:freshness-825767c` / `sha256:388cb328a7b08705b6b5e452d19a1814a878f0eb3a795b31da3e8dce12cc2596`, with source label `825767c`. The pre-deployment SQL backup and the prior Compose files are retained. Roll back by applying the retained production base + `freshness-825767c.override.yml` with the existing `/opt/china-fund-decision/.env`, then `docker compose up -d --no-build`; do not downgrade Alembic or remove the PostgreSQL volume. Preserve the new backup and reports during rollback.

The audit run still reports 2 moderate and 1 low frontend development-tree advisories, with no high/critical finding under the configured gate. No forced dependency upgrades were applied.
