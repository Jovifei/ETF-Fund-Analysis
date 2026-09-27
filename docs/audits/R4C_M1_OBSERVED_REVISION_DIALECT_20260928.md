# R4C M1 observed-revision dialect and deterministic IDs — 2026-09-28

**Status:** method specification committed before execution; evidence remains M1-only.
**Base:** accepted R4 methodology/evidence tip `ce7de47b9e168239c8fdbded221822f98359caa6` / tree `95e68e23d146f9012622c00c8cabaf2e645a8b02`.
**Scope:** define and validate evidence identities for repainting observations. No database model, migration, application integration, dependency, API, worker, frontend, Provider, real-data, actionable, or production change.

## Three identities

### `observation_id`

`observation_id` binds one complete causal computation: instrument, interval, prefix cutoff, input-bar hash, price-basis ID, engine/version, dialect ID, and qualification config ID. It may never use observation wall-clock time.

### `structure_key`

`structure_key` identifies an endpoint-based candidate within this dialect: kind, direction/mark, and causal source start/end bar identities. It does not claim permanence and excludes mutable geometry.

### `revision_id`

`revision_id` binds one observed payload: `observation_id`, `structure_key`, and normalized geometry/state payload hash. A geometry change produces a new revision while preserving the earlier revision in the history.

## Observed lifecycle

The validation vocabulary is deliberately observational:

- `OBSERVED_NEW`: first appearance or reappearance after absence;
- `OBSERVED_UNCHANGED`: same key and payload at adjacent observations;
- `OBSERVED_CHANGED`: same key with a different payload;
- `OBSERVED_ABSENT`: key was present earlier and is absent at this observation.

`OBSERVED_ABSENT` is not called invalidation. The pinned engine does not provide that claim. Earlier observations and revisions remain retrievable; no historical row is rewritten.

The committed validator is `scripts/validate_r4c_m1_r5_revision_ids.py`. It regenerates the frozen R4 synthetic corpus in a disposable environment, computes the three identities, checks deterministic reruns and complete-corpus collisions, compares platform-neutral semantic digests, and checks a resource budget proposal. The candidate remains evidence-only and is not a runtime contract.

## Resource budget proposal

The proposal is intentionally an M1 review item, not a production SLA:

- one warm 300-bar computation: `<= 250 ms`;
- complete 20→300 prefix sweep: `<= 2 s`;
- peak process RSS: `<= 384 MiB`.

Independent review must freeze or reject these limits after reading the Windows/Linux measurements. The runtime config remains disabled and engine-less.

## Exit boundary

M1 can move to `READY_FOR_SELECTION_REVIEW` only if deterministic IDs are collision-free, the observed-revision history faithfully preserves absence/reappearance, cross-platform parity holds, unknown volume remains fail-closed, and the resource proposal is accepted. Even then `M2_GO=false`; engine selection and M2 implementation require a separate reviewed authorization.
