# Local scheduling recovery and close-window delivery

Owner-authorized execution stage. Baseline main 166ec8c / deployed source 9fe9fe8.
Keep the canonical local data root, private configuration, account database and rollback assets.

## Contract

- Separate settled base preparation (13:55, 15:15, 16:10) from close-window updates (14:20, 14:30, 14:45, 14:50, 14:55, 15:00). A fast update validates source/config/scope/database identity, settled-session cutoff, history and feature content before reuse. It fetches new quotes and derives the board; it does not claim a new forecast fit.
- Persist slots, attempts and task references in a separate local SQLite ledger. Acquire the existing OS execution lock before claiming or recovering an attempt. Never steal a live lock by age.
- Windows wakes the dispatcher every minute with StartWhenAvailable. The dispatcher rechecks verified trading dates and prioritizes the newest due slot; superseded/missed slots remain explicit. Historical observations are never manufactured.
- Preserve exported immutable packages across upload failures. Retry the same still-valid package with exact manifest/receipt checks, bounded attempts and cooldown. Code/config/scope changes or expiry forbid reuse. Acceptance proves delivery, not authenticated consumption.
- Failed/partial inputs retain their actual status and existing market-quality gates. No formula, thresholds, calibration or actionable qualifications change. A blocked fast base falls back to full preparation with measured lateness, never hidden freshness promotion.
- Freeze and test a source SHA, obtain webpage GPT review through the existing same-project chat, then back up and deploy with immutable image identity. Preserve cloud scheduler disabled, research display local_bundle, authentication and rollback. Local task migration keeps the existing principal and credentials.
- Capture before/after read-only cloud metrics for all 14 research tables with PostgreSQL statistics identity. Two distinct verified trading sessions, full scheduled-slot evidence, bounded latency and stable services are required. Counters reset or incomplete evidence yield UNKNOWN, never zero-growth PASS. Normal login/phone/OOS remain separate.

## Delivery checklist

- [x] Failure-first ledger, recovery, fast-base, dispatcher and stability tests (final exact-source qualification remains below).
- [x] Implement ledger and full/fast execution hooks, upload replay and latest-slot dispatcher.
- [ ] Preview and test owned Windows task migration; preserve a valid XML rollback.
- [ ] Full backend tests, compile/static checks, relevant front-end checks, independent review and exact CI.
- [ ] Webpage GPT reviews current source and test evidence; resolve actionable findings.
- [ ] Freeze source, back up data/task, deploy and independently verify actual source/image/settings/receipt.
- [ ] Enable pinned local task, verify real execution and install bounded two-trading-day monitoring.
- [ ] Publish measured results with remaining calendar-dependent acceptance explicit.

Fast-slot target is 120 seconds from planned time to accepted receipt; full slots have a 600-second budget. These are acceptance targets, not provider guarantees. Failures and missed targets are reported instead of loosening data gates.
