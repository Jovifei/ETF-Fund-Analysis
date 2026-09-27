# R4C M1-R4 causal and lifecycle probe specification — 2026-09-28

**Status:** specification committed before execution; no result is claimed by this file yet.
**Base:** R3.2 evidence commit `208d7c10c98d686321d4774fd3bd2ba489b45ab9`, tree `55503f9d19299dee5b15f8f587df8aa4cf033f0d`.
**Candidate:** CZSC `v1.0.1`, pinned source commit `90372af035f01ed9f05070eadddd265b91c84d24`.
**Scope:** isolated Windows/Linux synthetic probes only. No project dependency, runtime integration, Provider, model, API, schema, frontend, real-data, canonical-action, actionable, or production change.

## Committed methodology before execution

The exact harness is `scripts/validate_r4c_m1_r4_causal.py`. It must be committed and hash-bound before any disposable environment executes it. The harness generates its own deterministic 300-bar daily fixture, so the committed file identity binds the fixture and normalization logic. Platform and timing metadata are excluded from semantic digests.

The harness records:

- source commit and environment identity;
- every prefix from the minimum probe history through bar 300;
- normalized FX/BI/ZS geometry, source endpoints, explicit `prefix_end_bar_id`, candidate causal IDs, first/last observation, changes, and removals;
- normal full suffix versus future-only suffix mutation at cutoffs 80, 160, and 240;
- separate positive-volume, true-zero-volume, and unknown-volume inputs;
- cold import/startup, warm full-run time, OS-level peak working-set/RSS, and failure status.

## Causal ledger contract

The candidate identity is content-addressed from kind, direction/mark, source start/end bar identities, and the fixed price-basis ID. It deliberately excludes observation wall-clock time and mutable geometry. The identity is a validation candidate, not a runtime contract. A structure's geometry can therefore change while its candidate identity remains available for classification.

The ledger separates:

1. structure event time from source bar endpoints;
2. engine confirmation time, only when pinned source semantics establish it;
3. first application observation time, represented by the first prefix in which the normalized object appears.

The probe does not infer an engine confirmation timestamp from first observation. Missing source semantics remain `NOT_ESTABLISHED`.

## Future and mutation comparisons

For each cutoff, the harness compares the structure set visible through the cutoff with the same source bars followed by a normal suffix and by a suffix whose bars strictly after the cutoff are mutated. It reports unchanged, changed, removed, and new identities. A future-only mutation that changes an already claimed confirmed structure is a blocker unless the pinned source contract explains the replacement.

## Required exit boundary

Only a complete and independently reviewed result can move M1 to `READY_FOR_SELECTION_REVIEW`. If causal confirmation, repaint/replacement, stable identity, volume semantics, or resource evidence remains unresolved, M1 stays `CLOSED_BLOCKED`. The committed qualification config remains disabled and engine-less throughout this stage.
