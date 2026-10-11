# Sector evidence local repair — 2026-10-11

Base: e722ad5. Worktree: E:/project/ETF-Fund-Analysis/.local/local-execution-20261011.
Local implementation authorized by Jovi; webpage GPT review pending. No production access, provider call, commit, push or deployment.

## Change

Sector observation is independently versioned v2, evidence contract `sector-evidence-v2-source-percent-cutoff`. Canonical grades, strategy formulas, thresholds, and strategy.json are untouched.

Market corroboration requires the existing `akshare` industry adapter identity (akshare.py name and `_parse_sector_frame` persist source percentage points unchanged), finite percent, known trade date, known acquisition timestamp no later than the board generation cutoff. Future trade dates/acquisition and older calendar dates are unavailable with reason codes; same-date freshness is deliberately conservative on non-trading days. Unknown source, Mock, missing cutoff/time and explicit unit conflicts are rejected. Percent is not rescaled; publication/source time remains unknown and upstream unit qualification is not asserted. SQLite naive acquisition follows the repository Shanghai storage convention. Malformed breadth is null instead of erasing a valid independent percent.

No new metadata is injected into persisted SectorSnapshot rows. Its fetched_at is passed into the optional builder. Queries remain read-only. Query admission first filters to the exact cutoff calendar date, existing AKShare industry source and acquisition <= cutoff; then sorts/deduplicates. Future-date, Mock and future-acquisition pollution cannot hide valid current evidence. No fallback to an older trade date.

Read-side incompatible core snapshots and old/missing sector evidence contracts receive an empty blocked sector projection. Core-compatible rows keep their grades. Saved raw payloads stay unchanged. Frontend hides all explicitly non-version-matched reads, old or blocked sector digests rather than showing contradictory strong-side text.

## Executed evidence

Python 3.12: existing demo-afdf6c2-20261009 venv, PYTHONPATH points at this actual worktree backend.
- Initial new regression: 12 failures (new cutoff API absent plus actual legacy digest retention).
- Compatible core + old/missing sector evidence regression: two additional failures reproduced before its fix.
- SQLite real-query admission regression failed before query-cutoff change, then passed with current/future-date/Mock/future-acquisition/older-date records coexisting.
- Sector admission, existing sector timing and soft-failure suites: **36 passed**, no skips/failures.
- Frontend decision-summary suite: **5 passed**.
- Scoped Ruff: PASS after import ordering correction.
- Changed Python modules compilation and backend static JavaScript syntax: PASS.

Coverage includes exact cutoff admission, future/missing acquisition, future/stale/missing dates, mock/unknown sources, unit conflict, finite-percent preservation, malformed breadth, missing cutoff, authoritative service generation cutoff, true service legacy/compatible reads and immutable original payload.

Full backend regression, full frontend/typecheck/build and independent webpage review remain parent integration gates. No market, license, PIT, calibration or device qualification is promoted; actionable stays false.
