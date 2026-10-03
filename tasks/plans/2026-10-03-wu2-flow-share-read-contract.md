# WU2 flow/share provenance read contract

Baseline: `422c5c403d7336d1f7f01307bb99d5b8f2e6f25e`. This is the separate,
bounded time/unit/source acceptance repair required by
`docs/planning/NEXT_STAGE_REMOTE_EXECUTION.md` section 4. Scope and version
choices were independently reviewed before runtime edits. It does not extend
S5–S7, acquire data, change strategy or establish investment eligibility.

## Reproduced gaps

- Any non-mock quote, including an unsupported source or missing flow contract,
  is currently emitted as observed with fixed CNY/share/percentage units.
- A quote with no flow values is still observed. Source and acquisition times
  are omitted, so the flow block cannot explain its own time boundary.
- Both scale selectors ignore the cutoff and prefer an older delta over a
  newer total that has no delta.
- Stored v109 flow blocks bypass a correction to the builder unless reads
  explicitly project their old contract as blocked.

## Version and compatibility decision

New builds use `etf-flow-share-v2` within
`decision-read-v110-flow-share-provenance`. Existing numeric keys remain
nullable; spot and scale have independent status/reason/provenance fields.
All original v109 JSON stays immutable and addressable by snapshot ID.

The existing board `legacy_snapshot_requires_rebuild` policy remains: older
boards retain historical_grade and display 数据异常 until an independently
authorized later rebuild. Their flow read projection has null numbers, an
explicit original contract/version, and a legacy-projection reason. It cannot
masquerade as a stored v2 observation. A v110 board containing a missing or
different nested flow contract is blocked at the flow boundary too. GET never
rebuilds, fetches, enqueues, mutates a snapshot, or writes a migrated payload.

## Frozen admission and time semantics

- Spot contract/source: exact existing `etf-spot-flow-v1` + `akshare:em:v101`.
  Shares use the existing exchange helper source allowlist. This validates
  adapter provenance only, not independent upstream units or real-data quality.
- One aware cutoff per board generation/live view; compare timestamps as UTC
  instants and trade dates as Shanghai dates. The pure view requires an aware
  cutoff. Existing caller support for naive board generation is normalized
  explicitly to Shanghai before invoking the new contract.
- Persisted naive timestamps follow the repository's existing Shanghai storage
  convention, including SQLite timezone stripping. The response exposes the
  assumption; host timezone cannot affect results or upgrade verification.
- Numeric values require a valid acquisition timestamp at or before the cutoff.
  Future source timestamps and future Shanghai trade dates are blocked.
  Missing/malformed acquisition time is blocked, never replaced with now.
  Explicit source time/trade date later than acquisition is inconsistent and
  blocked too. Exchange helper identity must match its stored SH/SZ exchange.
- Accepted spot data with known acquisition time but unknown source time can
  remain explicitly time-unverified research. Source time stays null; the
  `source_timestamp_missing` marker is honored even if storage used fetch time
  as a placeholder. No row-level fresh/realtime state is inherited.
- Scale selection uses the newest cutoff-eligible record, including records
  without a delta. A missing delta never makes an older total current. Reuse
  one selector in both callers; do not search older quotes for missing flow.
- Return finite numbers unchanged. Preserve true zero and signed cash flows;
  null stays null. Reject bool/nonfinite/malformed values. Negative share totals
  and invalid proxy prerequisites cannot produce a directional share label.
  Do not recompute premiums, deltas, ratios, or apply a second unit conversion.
  Directional proxies must agree with the signs/order of their stored totals,
  delta and ratio. Contradictory fields are not repaired into a new signal.
- Existing scale rows are mutable. The view describes current persisted
  evidence bounded by observation time, not historical PIT reconstruction.

## Frozen boundaries

No provider invocation/adapter expansion, schema or migration, quote/history
replacement, formula/threshold/grade calculation, qualification promotion,
actionable change, credentials, purchase, model call or deployment. Existing
grading and strategy output must match a baseline golden fixture excluding
only the explicitly versioned flow block and envelope contract identifiers.
No automatic rebuild of older snapshots is included.

## Test-first exit evidence

1. Fix failing pure-contract examples: exact/unknown/missing source and contract,
   independent mock blocks, absent/partial values, zero/sign, bool/nonfinite.
2. Test cutoff equality, future/missing fetch, explicit future source, unknown
   source with known fetch, UTC/Shanghai equivalence, date boundary, and naive
   storage behavior independent of the process timezone.
3. Test all existing exchange sources and both selectors: newest no-delta rows,
   after-cutoff acquisition and future dates; no older-delta substitution.
4. Exercise live service, new board, legacy v109, wrong nested contract, saved
   snapshot IDs and every horizon. Compare persisted JSON before/after repeated
   reads and count writes/task/provider calls. Preserve raw legacy records.
5. Compare fixed-input golden output outside flow/version metadata. Keep all
   qualification/research/actionable values unchanged.
6. Run focused and full backend regression, actual frontend typecheck/tests/
   build, required static checks and independent final review. Publish only
   to the existing branch and verify exact-head CI. Consolidate the completed
   S4-U05 CI receipt with this next documentation batch.

This repairs backend evidence/read semantics. No dedicated flow/share component
exists in the current Vue views; this batch does not invent a new UI feature.
Existing frontend callers must still typecheck/build and pass regressions.
