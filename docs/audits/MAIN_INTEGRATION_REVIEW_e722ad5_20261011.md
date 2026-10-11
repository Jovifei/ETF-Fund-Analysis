# Latest main integration audit — 2026-10-11

## Actual delivered identity
main and origin/main are e722ad5d351da05ad01abfb7d5d2d339a6b75773, merged2026-10-11 12:33:44 Asia/Shanghai viaPR43. Sector implementation commits890cfc9/1f9f5c2/26537af/d29f080 were authored2026-10-11 01:07–01:33. afdf6c2 is ancestor; existing main already includes all received sector code.

Remote and local feature/local-compute-remote-display-v1 both point to the same e722ad5: no additional implementation diff. Claimed d05babd is not an object in this repository. At review time no openPR delivers the architecture. This establishes delivered refs only, not whether another writer has unpushed work elsewhere. Do not merge an empty feature ref or treat it as snapshot synchronization delivery.

## Actually executed local verification
Independent fixed worktree; no business/test edits, provider activation or deployment. Four affected backend files55PASS/0FAIL/0SKIP,185.736s; frontend23files197PASS; typecheck/build/compileall and static app.js syntaxPASS. No new local full-backend or browser suite claimed.
Exact-source GitHub current runs38116630491(ci),38116630489(workspace-ci),38116630482(audit-platforms) SUCCESS; results imported/read through GitHub. Existing green suites do not cover the audit cases below.

## CHANGES_REQUIRED findings
1. P2 future/mock sector evidence admission: DecisionBoardService._latest_sector_market_evidence selects overall max trade_date, lacks generation/read cutoff, and prefers non-mock without excluding mock. aggregate_market_evidence_by_theme marks matched evidence available without date/source qualification. Pure synthetic actual-function reproduction: sector_name半导体,trade_date2099-01-01,source mock-sector,pct_change99 =>availabletrue,alignment supports_add,note AKShare_SectorSnapshot_optional_corroboration_via_taxonomy. actionable remainsfalse, but source/time evidence labels are incorrect. Require settled source/date/fetched_at cutoff and explicit units/qualification before readable corroboration; missing data remains unavailable.
2. P2 incompatible-board summary contradiction: actual read_latest call with synthetic FakeSession and an old-version/config snapshot returns read_contract legacy_snapshot_requires_rebuild and rowgrade数据异常, but sector_add_themes still科技 and digest偏强观察. Frontend reads sector digest without current read-contract guard. This is actual service-path synthetic reproduction, not production database evidence. Block or explicitly label old summary when current board incompatible; do not change canonical grades or silently fall back to older snapshots.

Existing tests omit these cases; test_read_path_fills_missing_sector_timing_without_touching_grades manually copies the fill branch instead of invoking read_latest. Add real service-path regression plus future/stale/mock/cutoff/unit and phase separation tests remotely; do not weaken gates or delete old failures.

## Runtime and next handoff
Read-only production inspection during review: still afdf6c2/image1c5f59a3, APIhealthy. No evidence e722ad5 deployed at that moment. No production switch/cleanup/refesh initiated by this reviewer; keep other writer's deployment separate.
Local-compute architecture acceptance pending actual committed payload/schema/pointer/auth/expiry/retention/client-consumption code, complete tests and shadow comparison. Seven claimed tests alone cannot substitute the missing delivered source.

Main is already the newest delivered code; no additional source merge or main rewrite performed. Review receipt published separately for remote author to repair both findings as a complete stage, deliver fixed GitHub commits and then continue architecture acceptance. Do not sign off this main as fully accepted solely because CI is green.
