# Local compute -> remote display SHADOW (2026-10-11)

## Implemented boundary

Default disabled `shadow-display-v1`; canonical Vue/API, providers, strategy and production remain untouched. A generation contains public board rows, every row's daily chart (public indicators, SR/studies, raw/research prices and basis/qualification/time metadata), and persisted market references. One explicit SQLite read transaction exports all projections at the board generation time. Public field whitelists exist at exporter and receiver; no holdings/user detail projection or production database synchronization is used. Current board identity/time must match. Unknown source timestamps remain absent; source market time is never inferred from fetch time. All displays remain research-only/actionable=false.

Immutable canonical JSON/SHA256 files bind board/chart/market to one manifest, code/config, local-research producer and WRITE_ONLY_SHADOW scope. Sequence/time replay gates, explicit expiry <=2h, finite JSON, universe/hash/path/size/collision gates precede publication. Atomic latest pointer is last, with previous retained. Managed hash-named generations rotate under an exclusive writer lock; latest+previous remain protected. Capacity fails closed if retained active data plus new bundle exceed budget. Process crash leaves lock fail-closed: operator verifies no writer before recovery. No automatic stale-lock bypass.

## Offline usable chain

Create a dedicated local root with `.shadow-local` ownership marker and an existing `research.sqlite3` database. Provision this database using existing application migration/bootstrap procedures in a separately reviewed offline environment. This feature never initializes or copies production DB.

Run existing Python runtime with `scripts/shadow_local_job.py --root ROOT --database ROOT/research.sqlite3 --code-sha SHA --force-offline`. It refuses non-Mock or non-test settings, runs audited Mock collection (refresh_bars bounded 120 days, refresh_quotes, refresh_sector_snapshots), then indicator/forecast/signal/board tasks; stops at the first non-success, exports persisted projections, publishes to ROOT/receiver, verifies same manifest and writes public bundle.json. Optional `--sync-url https://HOST/api/shadow/sync` uses SHADOW_PRODUCER_TOKEN environment credential; no URL secret, redirects, plaintext HTTP or credential output. Network timeout and response sizes are bounded.

`shadow_snapshot.py export/publish/compare` also accepts already generated public projection files for offline receiver diagnosis. The receiver GET `/api/shadow/bundle` is authenticated with existing database-backed user sessions, cache private/no-store, and returns the complete same-generation consumer document. Expired/unavailable bundles return explicit HTTP410, without fallback. POST `/api/shadow/sync` uses a distinct >=32-character producer credential, which cannot read bundles or replace user/admin authentication.

## Scheduling and configuration

Explicit `register_shadow_task.ps1` registers 14:30/14:45/14:50/14:55/15:00/15:15 Windows tasks with supplied Python/workspace/local root/database/SHA; optional bounded slots. Existing verified XSHG calendar gates runtime; unverified/nontrade days or times outside 14:20–15:30 skip. At most eight slots, <=300-second due window, repeated completed slot skipped, Windows overlapping task instances ignored. No GPU or running Codex chat required.

Receiver settings: SHADOW_SYNC_ENABLED=false; dedicated writable SHADOW_SYNC_ROOT; exact SHADOW_SYNC_CODE_SHA and SHADOW_SYNC_CONFIG_HASH; secret SHADOW_SYNC_PRODUCER_TOKEN; bounded bytes/request/generations. Enable only after review. Code currently restricts jobs to offline Mock; real provider activation requires separate qualification/integration. No paid API or live network has been invoked.

## Verification boundaries

Tests cover atomic interruption, immutable collisions, replay, concurrent busy, bounded rotation, envelope/hash/version/NaN/expiry/private rejection, authenticated read vs producer write, dedicated DB refusal, calendar and HTTPS gates. A temporary Mock database exports real persisted read_model projections, HTTPS client injects an offline FastAPI transport, actual DB login establishes a cookie session, and all three returned parts compare to the exact manifest hashes. This proves the offline shadow chain, not production/UI/phone/provider qualification.

Windows task registration/execution, actual HTTPS transport, production receiver enabling, real-data jobs, canonical UI switch and mobile acceptance: NOT_RUN. Main UI remains unchanged.

Manifest supports only `1d`; 1w/1mo/5m/15m are explicitly unsupported in this SHADOW stage. Chart qualifications remain UNKNOWN and all cost overlays false. Public indicators/studies are synchronized for inspection, not trading approval.

`source_snapshot_time` means the persisted board snapshot generation timestamp, not a verified exchange/provider observation time. Each market reference carries its actual persisted source_timestamp; missing values are None with `source_time_unknown`, never substituted by fetched_at. Qualification remains UNKNOWN. Local job settings force LLM/analysis/OCR/bridge/daily-review off. Receiver recursively rejects unsafe actionability/qualification flags even when hashes are valid.

The new real EtfChart component test consumes a JSON fixture generated by Python `project_chart`; it exercises raw/research switching, MA5 and enabled research SR controls, with no cost prop/overlay. Existing canonical components are not changed.

Task registration accepts optional explicit HTTPS `-SyncUrl` and passes it to the job. URL credentials/query/fragment and non-sync paths are rejected. Without SyncUrl, scheduled runs remain local only; with it, the accepted generation is uploaded using the environment credential. Registration remains NOT_RUN. Local collection is Mock-only; no real Provider fetch occurred.

## Request HMAC authentication followup

Sync now requires both existing write-only bearer and independent HMAC signing key. Server configuration SHADOW_SYNC_ACTIVE_KEY_ID / SHADOW_SYNC_SIGNING_SECRET accepts exactly one active key ID; rotation immediately rejects previous IDs. Producer environment SHADOW_SIGNING_KEY_ID / SHADOW_SIGNING_SECRET signs the exact transmitted body. Keys must remain secret environment configuration; never reports, manifests, URLs, receipts or logs.

Domain-separated HMAC-SHA256 binds WRITE_ONLY_SHADOW, POST, exact sync path, key ID, canonical UTC seconds timestamp, 128-bit random nonce, and SHA256 of actual request bytes. Receiver constant-time verifies within +/-120 seconds before JSON publication. Durable nonce reservations under store/nonces survive process restarts and rejected bundle publication; atomic exclusive creation and reservation lock reject replay/concurrency. Reservations expire after signed timestamp+241 seconds; at most3000 are retained. Only managed hash files are expired; root DB is untouched. A crashed reservation lock fails closed and requires operator verification/recovery. Actual TLS/network/rotation of real keys: NOT_RUN.

Operational hardening: Mock collection explicitly targets a verified settled session and keeps real acquisition time.420 calendar-day history supports existing warm-up. Full-coverage Mock quotes retain partial/degraded status and UNKNOWN; only offline display transport may continue, failed/missing/incomplete outcomes remain blocked. CLI requires exact clean application checkout matching suppliedSHA. Byte-budget GC also reclaims unprotected generations before reaching generationcount; latest/previous remain protected. Default64MiB covers three bounded16MiB publications andmetadata/nonce overhead; configured smaller budgets failclosed. ActualtemporaryMock CLI run succeeded; no realdata or remoteupload executed.
