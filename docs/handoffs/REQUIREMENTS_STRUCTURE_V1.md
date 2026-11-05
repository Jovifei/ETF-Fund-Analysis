# REQUIREMENTS — structure_v1 acceptance criteria

**Companion:** `HANDOFF_STRUCTURE_V1.md` (canonical under `/workspace/etf_structure_features/`; in-repo `docs/handoffs/`)  
**Zone:** Asia/Shanghai · **Updated:** 2026-11-05

An item is done only when its acceptance check passes.

## Phase A (display-only)

- [x] Feature wiring committed (`5844e828`) and tip handoff (`9a072f2`) **pushed** to `origin/feature/structure-v1-wyckoff-dow-atr`.
- [x] Merged into **review** baseline via PR **#64** (`ecc26155`) — **not** live/main.
- [x] Daily shadow sample **34/34** for 2026-11-05 with schema `structure_v1`.
- [x] In-repo real ATR/Dow/Wyckoff proxies (stubs removed); shadow builder `build_shadow.py` reproducible.
- [x] Board `_row` soft-fills `structure_v1` from history (no sidecar required for three columns).
- [x] Pytest `backend/tests/test_structure_v1.py` covers proxies + soft-fill.
- [x] Dry-run email/board path OK for 2026-11-05.
- [ ] Each new session: shadow rebuilt 34/34 for that date.
- [ ] Slim attach before strategy email render on parallel days.
- [ ] Email 11:40 / 14:30 / 14:45 can show structure research columns without changing five-档.
- [ ] Board旁路 serves +3 structure columns; not in live sort keys that alter grade.
- [x] `assign_grade` / live CONFIG_HASH / SHA `a0d52e44` unchanged.
- [ ] Parallel display observed for **≥3 trading days**, then review before any **live** merge.
- [ ] Live sync task must **not** point `SHADOW_SYNC_CODE_SHA` at feature tip until user-approved cutover.

## Email & site ops

- [x] Weekday strategy mail slots documented: **11:40 / 14:30 / 14:45** from `jovi-bot@mail.grokbot.com` → `zxf977191131@gmail.com` + `977191131@qq.com` (direct send).
- [x] Site path documented: outbox `bundle_<seq>.json` → receipt **`accepted`**.
- [ ] Ongoing: slot failures (Jovi offline, blocked send, missing receipt) investigated without waiting for a nudge when standing orders apply.
- [ ] ~17:30 research digest: **not wired** until user confirms new routine.

## Phase B0 (research soft-weight)

- [x] Selection walk-forward recorded (2026-06-10→10-22); soft_c 5d wr **50.83%**; structure_heavy 5d **52.91%**; soft_c better on 20d (**53.72%** vs **49.25%**).
- [x] Holdout frozen-weight recorded; verdict **`WEAK_PASS_KEEP_FROZEN`** (soft_c 5d ~**62%** but n tiny; pnl loses to momentum).
- [x] Week(~5d)/month(~20d) comparison recorded; month holdout insufficient as of 2026-11-05.
- [ ] Holdout grows until **10d and 20d** forward windows exist.
- [ ] Soft overlay beats **both** baselines on 5d **win_rate and avg_pnl_active** with adequate n before promote talk.
- [ ] User bar **stable win-rate > ~60%** — **not met** → do not claim live decision “可行”.
- [x] Proposed weights only in JSON/FORMULA; not written into live `strategy.json`.
- [x] Structure weight block **> MACD** in board bypass design (trio 0.40 > macd 0.10).
- [x] Production MACD remains **12/26/9**.

## Phase B1 / B2 (not started)

- [ ] B1:旁路 `shadow_grade` column; live five-档 still frozen.
- [ ] B2: explicit user approve + new CONFIG_HASH + merge plan before live `assign_grade` change.
- [ ] Optional: `replay_assign_grade.py`旁路 CLI.

## Process / handoff

- [x] Durable handoff for another AI (ETF Bot + Grok fuller copy).
- [ ] Box/feature follow-up commit carries fuller handoff + REQUIREMENTS (this pass).
- [x] Feature branch pushed (`9a072f2`); review PR merged.
- [x] **No** live/main grade merge.
- [x] No Cursor CloudAgent / work-quota for this track.

## Explicit non-goals

- Editing live five-档 thresholds “just to try.”
- Treating short holdout ~62% as promotion proof.
- Replacing live MACD with 21-period without dedicated experiment + approve.
- Force-push or silent production cutover.
- Treating `review/*` merge as live deployment.
