# WU2 flow/share provenance and cutoff repair

Baseline: `422c5c403d7336d1f7f01307bb99d5b8f2e6f25e`, existing branch
`codex/remote-stage-s8f0-s2-20261002`. This follows the independent WU2
time/unit/source acceptance requirement, with a separately reviewed
[bounded plan](../../tasks/plans/2026-10-03-wu2-flow-share-read-contract.md).

## What the source review found

The old helper admitted every non-mock quote as observed, even when its flow
contract was absent/unsupported or every flow number was null. It assigned fixed
CNY/share/percentage units without checking the accepted adapter contract. The
flow block omitted its own source/acquisition times. Both scale selectors could
substitute an older delta for the newest total and ignored the read cutoff.
Already persisted v109 payloads bypassed any fix made only to the builder.

Offline examples reproduced those behaviors without market requests. The new
cutoff API initially failed all 33 contract cases; the seven caller/compatibility
tests then failed before caller changes. A later 56-case adversarial run exposed
16 failures, including fake v2 labels without provenance, contradictory proxy
direction, numeric overflow and acquisition chronology. Those failures are
retained in the execution evidence. JSON generation mismatch and nonpositive
IOPV each had separate failing regressions before their fixes. Final review also
reproduced three failures for naive new-board envelopes and extreme timestamps;
normalization and a blocked-state roundtrip now pass without erasing independent
share evidence.

## Versioned result and compatibility

- Newly generated boards use `decision-read-v110-flow-share-provenance`; their
  nested flow contract is `etf-flow-share-v2`. Existing numeric fields are
  nullable and retain their values/signs, without a second unit conversion.
- Spot admission requires `etf-spot-flow-v1` and `akshare:em:v101`. Scale
  admission reuses the three existing exchange-helper source identities and
  their SH/SZ pairing. This asserts adapter provenance, not upstream data or
  investment qualification; `unit_qualification=not_asserted` is explicit.
- Each component has its own status/reason, source, source time or trade date,
  acquisition time and unit. One blocked component does not erase another
  component's valid evidence. Empty values are missing, not observed.
- Acquisition must be known and no later than the single read/generation
  cutoff. Explicit source time/trade date cannot exceed acquisition or cutoff.
  Accepted fetch-time observations with unknown source time remain explicitly
  unverified, with null source time. Fetch time never becomes source time.
- Aware timestamps compare as instants, trade dates use Shanghai, and naive
  stored timestamps use the repository's documented Shanghai convention with
  an explicit assumption field. No process-timezone dependency is intended.
- The shared selector chooses the newest cutoff-eligible scale including
  missing-delta totals. It cannot replace a new total with an old delta.
- True zero/signed flows remain intact. Booleans, overflow, nonfinite values,
  negative current share totals and nonpositive IOPV cannot become valid numbers. A proxy
  needs consistent stored total/delta/ratio direction and valid prerequisites;
  the response does not recompute those figures or invent a direction.
- Mutable source scale rows do not support historical PIT reconstruction. The
  response explicitly describes current persisted evidence bounded by observed
  acquisition time, not historical PIT.

Existing v109 snapshot JSON remains unchanged and addressable by snapshot ID.
The existing version-mismatch policy retains historical_grade and marks the old
board 数据异常 / legacy_snapshot_requires_rebuild. Its flow projection is blocked,
retains the original contract and board version, and separately identifies the
v2 read-projection contract. It is not a relabelled stored v2 record.

Saved v110 views also validate their exact recorded fields, units, safe flags
and cutoff against the authoritative snapshot-row generation time and JSON
generation time. Missing/mixed version uses `flow_contract_unverified`; malformed
same-version evidence uses `saved_flow_contract_invalid`. This reapplies only
field admission to saved evidence: no DB hydration, Provider, research formula,
task, write or automatic snapshot rebuild is performed during reads.

The version change has a visible future rollout consequence: old v109 boards
remain legacy until a separately authorized refresh creates new v110 snapshots.
This batch neither deploys nor refreshes production data. Old records and raw
stored JSON remain available for audit. No schema or migration changes.

## Validation state

- Focused new/existing flow suite: **91 passed**, no skips/failures.
- Independent baseline golden fixture was captured and replayed twice before
  runtime edits. Complete live and board rows, excluding only flow_share,
  match after the change. Live sample remains 可加仓; its unqualified board
  remains 数据异常; both remain actionable=false.
- Golden fixture SHA-256:
  `1b88686c785375e2173320ffaa9acf4a04bc44826d1530db5e092864832bfd8a`.
- Snapshot-ID/latest/per-instrument/every-horizon reads, actual HTTP response
  compatibility and private no-store headers pass. Repeated legacy/mixed reads
  leave persisted JSON unchanged; captured statements are SELECT-only.
- Actual Vue typecheck, **116 tests / 20 files**, and production build: PASS.
- Scoped Ruff, Python compilation, JavaScript syntax and whitespace: PASS.
- First aggregate completed with **1568 collected / 1557 passed / 11 existing
  skips / 0 failures**, 554.312 seconds. It began before the final time-edge
  corrections and is provisional evidence only. A clean final aggregate
  was rerun against the corrected frozen runtime. A second intermediate run
  also passed 1572 collected / 1561 passed / 11 skips / zero failures before
  the final UTC-underflow guard; it too is retained as provisional evidence.
- Independent timezone probes matched under UTC, Shanghai and Los Angeles.
- Final runtime/test independent review: **PASS**. The reviewer independently
  passed 91 focused cases, 110 extreme timestamp combinations, and 10 attempts
  to misuse the safely empty invalid-time state.
- Final accepted aggregate: **PASS**, exit 0, **1576 collected / 1565 passed /
  11 existing skips / 0 failures / 0 errors**, 551.366 seconds. Runtime hashes
  below remained unchanged throughout this run. All 11 skip identities match
  the exact 422c5c4 hosted predecessor. JUnit SHA-256:
  `8cce0c47c9745454d06820498f766f12f9891f6dde22814f736e8c4da3c73093`.
- Complete 17-file source/test/receipt review: **PASS**. Final JUnit and all skip
  identities were independently verified. Exact new-head hosted CI remains
  **PENDING PUBLICATION**; no predecessor CI substitutes for the new commit.

The related S4-U05 predecessor is independently closed at exact commit 422c5c4:
see its [hosted receipt](S4_U05_CHAN_SETTLEMENT_DISPLAY_20261003.md). Its CI totals
and screenshots are historical predecessor evidence, not this candidate's CI.

Real-data/units/PIT qualification remains UNKNOWN, predictions not calibrated,
and actionable=false. No new provider access, credentials, purchases, deployment,
registry publication, runtime activation or Windows/local hub sync is claimed.

## Reviewed runtime identity

Final runtime SHA-256 values, frozen before the accepted aggregate run:

- flow_share_research.py: `883f7294080fc87cf92b005fdaaf3380413c1e8dc9e82ffa7f2e92ec7d9e3f2f`
- decision_board_service.py: `ffccf3676c4162c452a6cb648375bb037e324a04f1be0552199d1cad6b6df63b`
- signal_grade_service.py: `11de4871c98b4a4c18036223d135eadffb26b111f23d144d92372f6d548757ae`
