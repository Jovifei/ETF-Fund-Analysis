# Iteration 71 diagnostic cleanup

Jovi authorized checking server services and deleting unnecessary remnants on 2026-10-02. The two v106 ETF diagnostic API containers were not referenced by the website reverse proxy. Their ports were 18086/18087; the live ETF site routes to 8080. They were separate Compose projects but shared the `api` alias on `china-fund-decision_backend`.

Only these containers were stopped, verified exited, and removed without `-v`:

- `ba918329543653303a0a97751635412b60611a965147bd7cfc603acf6a04bed3`
- `3e33b8d81bfb3030db39a9ce5fa6d4143de40a48ee17731a0cbb2f06327f6d8b`

An additional obsolete v106 diagnostic container, already exited for 12 days and unused by website routing, was inspected and removed without `-v`: `7f8c936914c178faa0ca910588454f09a0af80e581c84d3d31cf3432938097e9`. It used the same old image with isolated source/config/script bind mounts and shared reports/backups. These host files and image were retained.

Post-cleanup verification: both IDs absent; backend network contains only production API/worker/scheduler and ETF PostgreSQL. Public ETF health returned `status=ok`, version `1.0.8`, production, auth enabled. Production container identities were unchanged. Shared reports/backups, images, database volumes and other applications were retained.

Inventory also identified active Star Photo and Tesla/Jourvolt services. No medicine-box Docker container was identified on this host; its deployment location remains unverified. Unidentified stopped containers were not classified as disposable.

R4 namespace blocker is cleared locally. R3 candidate remains source `3a13575f58ae6f8aad0face1a8e42391d2356518`, tree `70c5ea87fc84ed027202c8df0622f5e44f717a9e`; candidate is not deployed. Next: fresh backup using reviewed candidate backup script via stdin with explicit production Compose and backup paths; no retention cleanup. Continue restore/migration/smoke/rollback gates before switching production.

## R4 backup result

The first unbuffered stdin invocation returned exit 0 but published no archive. It is NOT accepted. The corrected invocation read the complete exact candidate script before executing bash, with explicit production Compose project, env-file path and backup directory. No production script file was changed and no retention pruning ran.

- Archive: `/opt/china-fund-decision/backups/fund_decision_20261002_002706_pZSmts.sql.gz`
- Size: `341436962` bytes
- SHA-256: `4f5fbc458cefcfa5176326f0e70df88934a09c2cabac4c8248c62e71bd79de53`
- Mode: `0600`
- Recorded file time: `2026-10-02 00:33:16.484241546 +0800`
- Source PostgreSQL container: `china-fund-decision-db-1`; pg_dump `16.15`
- Backup exit: `0`; independent `gzip -t` and checksum-file verification: PASS.
- Live ETF health after verification: `status=ok`, production, version `1.0.8`, auth enabled.

R4 backup archive validation PASS. Restoreability remains NOT_RUN until R5; R6 smoke, R7 rollback rehearsal and production switch remain NOT_RUN. Real data UNKNOWN; no automatic trading.
