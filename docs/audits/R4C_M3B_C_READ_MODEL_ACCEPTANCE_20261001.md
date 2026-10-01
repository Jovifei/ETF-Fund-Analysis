# R4C M3B-C persisted read model — local acceptance receipt

Date: 2026-10-01 (Asia/Shanghai)
C2C task: `c2c_a1d7`, iteration 70
Remote plan base: `f6ac2af15373be38797fb57dd6b2aff15b353fa2` / tree `d866390ca5a0fcb852b574b1855a1ad35494e1e8`
Execution branch: `codex/r4c-m3bc-relocated`
Implementation/release flags from remote: `M3B_C_IMPLEMENTATION_GO=true`; `M3B_C_RELEASE_GO=false`; `M4_GO=false`; `MAIN_INTEGRATION_GO=false`; `PRODUCTION_GO=false`.

## Result

M3B-C implementation and local verification gates pass. The iteration-70 candidate is ready for GitHub exact-head review. Remote code review is pending at this receipt's handoff point. Production deployment remains gated behind a separate release plan and its backup, restore, rollback, and live-smoke evidence.

The checkout is isolated at `E:\project\ETF-Fund-Analysis\.local\etf-r4c-m3bc`, within the project directory as Jovi requested. The C-drive source worktree and the Owner `main` checkout were preserved. Sixteen pending files were copied from the prior execution checkout and SHA-256 checked before work continued.

## Changes verified

- Read the latest persisted D/W/M Chan observation through one canonical read service. The result is explicitly `latest_persisted_observed_revision_not_historical_pit` and does not claim historical point-in-time visibility.
- Validate stream head, observation, full structure revision set, and transition evidence. A predecessor with a regressed cutoff or cutoff time returns `persistent_evidence_corrupt`.
- Determine reappearance from the latest earlier non-null transition for the same stream/key, ordered by observation sequence and limited to one row. Verify the witness observation payload/hash and complete revision set, namespace, and transition-to-key/revision link; corrupted evidence fails closed.
- Add one authenticated private GET for D/W/M with `Cache-Control: private, no-store`. Reads use persisted evidence and have no `as_of`, refresh, enqueue, engine, Provider, model, or database-write path.
- Replace the competing Kline GET-time legacy `chanlun` calculation with persisted R4C counts and bounded metadata. Missing evidence remains unavailable; `segments=None` and engine confirmation stays `unknown`.
- Remove only `USER_FACING_READ_MODEL_NOT_INTEGRATED`; disabled, blocked, selected-disabled, and runtime-disabled flags remain in place.

## Verification

| Gate | Result |
|---|---|
| `backend/tests/test_chan_m3b_read_model.py` on Windows Python 3.13.14 | 24 passed, 1 PostgreSQL fixture skipped, 1 warning |
| Full Windows repository pytest | 1,399 collected; 1,376 passed; 23 skipped; 0 failures; exit 0 |
| PostgreSQL 16 worker → private GET + integrity corruption + no-DML gate, Python 3.12.14 Linux | 1 passed; 1 warning; disposable database was loopback-only |
| M2 CZSC 1.0.1 Windows 3.12.9 / Linux 3.12.14 | semantic digest matched: `091254d34ddfeeadc85cd0b17e035295bfc32f8a0cebc6776440f10be82aaeac`; deterministic 300-bar output and all resource limits passed |
| R5 Windows 3.12.9 / Linux 3.12.14 | semantic digest matched: `0f4ae0322b5d390c41e618da4c342abea66baac30bce4ccfe4a5f0d713cff76f`; history digest matched: `d637b4f80c749db48d06dfafe3762216d684ff2827149b4024a3de3f814fc1e9`; observation ledger digest matched: `a0c4496e762213b9a698dac1a5ec37342c2765da3709a6bdea70553a76d91c5f` |
| R5 collisions and resource limits | ordinary observation/structure/revision collision count 0 on both platforms; injected weak-ID collision self-test detected the collision; RSS/prefix/warm limits passed |
| Static checks | scoped Ruff, `python -m compileall -q backend/app`, `node --check backend/app/static/app.js`, scoped secret scan, and `git diff --check` passed |

The first full Windows run had one timeout in `test_paddle_response_then_sleep_worker_is_cleaned_up`. The test passed in isolation and in the second full run; no OCR code or tests were changed because that subsystem is outside the iteration-70 authorization.

## Evidence boundary and next gate

All runtime evidence here is synthetic/test-only. No Provider request, real-market-data qualification, production database, deployment, or trade was performed. Real-data qualification remains `UNKNOWN`; `actionable=false`; automatic trading is absent.

The exact code/evidence candidate SHA and tree are recorded in the C2C iteration-70 execution evidence and verified GitHub readback. Submit that exact head for remote review. `M3B_C_RELEASE_GO=false` remains in effect until remote review passes and a separate release-gate plan authorizes backup/restore rehearsal, rollback rehearsal, and live smoke.
