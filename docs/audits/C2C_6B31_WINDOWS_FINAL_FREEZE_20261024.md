# c2c_6b31 — final upstream Windows-fixture reconciliation (2026-10-24)

Status: REVIEWED / EXACT FINAL-SHA CI TO BE RERUN. This is an additional bounded reconciliation on the **same** integration task, not a new local workspace or a deployment.

## Why one more integration parent was needed

While our earlier integrated PR54 head `0b63ce4bf0d468d5b816017ff3ee785ca4eebb55` successfully completed all four GitHub Actions suites (main `ci` `40052900495`, `workspace-ci` `40052900471`, `audit-platforms` `40052900445`, `postdeploy-ci` `40052900453`), Owner's original PR51/52 independently progressed. Our test-only tree was safe, but those later changes address a distinct, real Windows all-tests failure and must not be silently omitted from an integrated acceptance candidate.

Frozen newer inputs, GitHub-read:
- `main`: `1a4b6652f49c412145d12812fa02820ba0a80991` — not modified.
- PR51: `bdb556f9c60254b2e8e866f256386b062e2ab7ab`, one commit beyond `ba86baf9`.
- PR52: `109253e8c4ccb5c7c8e21b22d0911398cd8beb16`, tree `7e0e9b83f09067b757746e4a5caae2c879823254`; merge parents `82916e5a` + `bdb556f9`. It includes newest PR51 and docs.
- PR53 unchanged final `fdaf5426585d64800dbff60656797cd75306f19e`.

Source diff PR52 `82916e5a` → `109253e8`: two test files `backend/tests/_ocr_workers.py` and `backend/tests/test_holding_import.py`, plus current STATUS/HANDOFF/progress/audit/todo documents. **No production OCR, Provider, strategy, database, account/holding model or runtime config changed.** This worker is a test-only spawn target that sends the same synthetic empty success and sleeps 2 seconds, imported from a lightweight module. The original test still has a 2.0-second hard deadline and an active-child before/after cleanup assertion; it now avoids importing a heavy ORM-backed test module into the Windows spawned process.

The Owner's GitHub audit documents an actual local Windows full suite on `ee6513a`: **2638 items / 2613 passed / 24 skipped / 1 failed** (process exit 1), with `test_paddle_response_then_sleep_worker_is_cleaned_up` returning unavailable. The precise failure reason in that original assertion was not captured, so do not falsely label that exact failure as proven timeout. Separate spawn experiments report heavy module import often near the deadline and lighter worker completing consistently; 69 focused OCR-module tests completed with 2 skips. This is **Owner-supplied historical evidence**, not a new Windows run by the remote agent or an acceptance of private OCR data.

## Correct merge policy

Advance only our independent `codex/c2c-6b31-integrated-20261024` branch by a **two-parent commit**: first parent `0b63ce4b` (already tested stage), second parent latest PR52 `109253e8`; create Git tree from newest PR52 tree, overlay only our previously reviewed `test_display_cache_rolling.py` blob `928b56e802b2fb559bc08368254e20274097f91b` (PR51 `watch_atomic_peak` plus PR53 fdaf current/previous/hold/retention assertions), the original c2c_6b31 RED and source reconciliation notes, this review, and the task's updated handoff.

Do not override latest PR52's complete versioned-auth E2E, receiver guard, responsive checks, new OCR worker fixture, or documentation. Preserve Vite 7.3.7 and `npm audit --audit-level=high`. No merge/main/deploy or changes to any original PR branches.

## Exact CI and acceptance scope

The earlier head `0b63ce4b` passed GitHub `workspace-ci` with Vue 228/228, mock Chromium 44/44, controlled authenticated 6/6, responsive 18/18, audit/type/build PASS; main `ci` JUnit **2638 total / 2627 passed / 11 skipped / 0 failed/errors** and Docker build+smoke PASS; cross-platform and postdeploy testing SUCCESS. Its source tree is `6d73b84b65782ddd2de79f2653bb34ae649f606b`. These results are **historical and MUST NOT be copied as final-pass status after the new merged SHA**.

Rerun all four existing workflows on the new commit. Inspect exact run IDs, no skipped gates, JUnit, npm audit, Vue/type/build, Chromium Mock/auth/responsive, Windows/Postgres jobs, build, image smoke and source tree. GitHub Actions' Windows bridge tests are not a substitute for the independent Windows *full* pytest/OCR acceptance; that remains pending local Codex. If errors occur, keep failing receipts and repair on independent branch only, not by changing production deadlines or dropping tests.

No accounts, credentials, private data or live Provider access. Cloud database/production/phone/natural two-trading-day and data license/PIT/OOS/calibration gates remain PENDING/UNKNOWN; `actionable=false`, `not_calibrated`; no auto trading.
