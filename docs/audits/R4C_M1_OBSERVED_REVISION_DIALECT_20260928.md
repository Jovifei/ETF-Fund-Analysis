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

## R5 execution receipt

The committed validator is `f344514d69b14805a9d112190ab228569cb6dc42`, tree `406b6bb4df5a8b14a4ac0efa2038f5babbceba2d`, with script SHA-256 `D2F516F4CF2F185414393F03024ED70441674D42B822CBDB57A3D93FD88191E1`. It ran only with the pinned CZSC wheels in disposable Windows/Linux environments.

| Environment | JSON SHA-256 | Semantic digest | Observations | Records | Revisions | Collisions |
|---|---|---|---:|---:|---:|---:|
| Windows CPython 3.12 | `794B13380449FE4E0634266EC309318B0DBC45554AA54943E4A65EA2D75EB50F` | `bc21ba9c16f0756682a9a1c0bccf142b21c889b2fa6bbd7bb99e524f9ba1ef8c` | 281 | 6604 | 6568 | 0 |
| Linux Python 3.12 | `C1C65C42E95649F0D9BC4B0901FC1AF78F319210CC831C177A828586240BA0B3` | same | 281 | 6604 | 6568 | 0 |

Both same-input reruns were deterministic. Transition counts matched across platforms: `OBSERVED_NEW=87`, `OBSERVED_UNCHANGED=6481`, `OBSERVED_ABSENT=36`; 21 reappearances were retained as new observation bindings. No historical revision was overwritten. The proposed resource limits passed on both platforms: Windows warm `4.582 ms`, prefix sweep `1301.901 ms`, peak working set `138,805,248` bytes; Linux warm `4.150 ms`, prefix sweep `1249.783 ms`, peak `VmHWM` `217,919,488` bytes.

`engine_confirmation` remains `unknown`, while `application_observation_status` is `observed`. This is an evidence-only observed-revision validation, not engine selection or runtime integration. M1 remains `CLOSED_BLOCKED` and M2 remains false until independent review accepts the dialect and its resource proposal.

## Exit boundary

M1 can move to `READY_FOR_SELECTION_REVIEW` only if deterministic IDs are collision-free, the observed-revision history faithfully preserves absence/reappearance, cross-platform parity holds, unknown volume remains fail-closed, and the resource proposal is accepted. Even then `M2_GO=false`; engine selection and M2 implementation require a separate reviewed authorization.

## R5.1 identity hardening boundary

The R5.1 validator must use a dialect-native, namespaced `structure_key` that binds instrument, interval, engine ID/version, dialect ID, config ID, price basis, structure kind, direction/mark, and causal endpoint identities. Observation, structure, and revision IDs must each be checked against canonical preimages in separate collision maps. Every cutoff receives an observation ledger row even when no structure exists; absence is an adjacent transition, and reappearance creates a new observation binding. The validator must prove namespace sensitivity and keep `engine_confirmation=unknown`.

The authoritative checked-out method file SHA is `D2F516F4CF2F185414393F03024ED70441674D42B822CBDB57A3D93FD88191E1`. The earlier bounded chunk release was serialized as text and had a separate transport hash `17F28DA499CD255DDCF0C17ADFB30F3A6D76F31B9C0253DCE55A244214D1D004`; that transport hash is not the committed file SHA.

R5.2 corrects collision validation to retain canonical JSON preimages in each namespace map. An ID is now a collision only when the same ID maps to different raw canonical payloads; a hash of the payload is not used as the collision preimage.

## R5.2 collision-preimage receipt

The corrected method is `ce1a03a9a95b1a108823465128a09ea39ea2966a`, tree `b4348edbe3d418b6070369262a0c6880286e9485`, method SHA-256 `4FEEEA4340EDE67A82ED4E6C9984F525DEAA5BD3CA53D488B698665503907AFC`. Final Windows/Linux JSON hashes are `EC590CAF5F004D88C72B1AD22F3E0007E2B9E2E9B6268D1252BEA63D9825F67E` and `F3969E718BFFC8422C2040C58046DEEDC6519EFD43EA93FA425ACD4DFE9CDA04`; semantic digest remains `9346d77b4d0477a3434238924b4b63c939c098feb9f27321313de79bf28f8b54` on both platforms.

Each namespace now maps its ID to the raw canonical JSON preimage. Windows/Linux both report observation, structure, and revision collision counts of zero; namespace sensitivity, 281 observation rows, 6604 records, 6568 revisions, 36 absence transitions, 21 reappearances, and the accepted resource budget remain passing. Engine confirmation remains `unknown`; M1 remains `CLOSED_BLOCKED` and M2 false.

R5.2.1 adds a checker self-test with an injected weak ID: two distinct canonical preimages map to the same test ID and the checker reports `collision_count=1` on both Windows and Linux. This proves the collision checker can detect a collision rather than merely reporting the production SHA-256 corpus as collision-free. The production namespace formulas remain unchanged.

## R5.1 identity-hardening receipt

The corrected method is committed at `f151e262d97f0f20addc1faf4773dfcb46742d8a`, tree `dfbee537778920ad1745ccbf558e72631a6beca6`, with script SHA-256 `544156B9A865D7768635F6CF0A20513947F00AD49EB676082C04B35E269D3883`. The final evidence tip is `3751476667e087de159a8dd73f3f6dd7e760babc` / tree `f14c75aa36856a6e8b4fa51f57436884dbc7586b` before this R5.1 receipt update.

The Windows and Linux final JSON hashes are `DC6E9D1E767CD139E80F0B9A729D5F70FB1248924E9EE4AAF20B9B6EA84F51E2` and `1E31DE5406A20AB755CCC56EB4F2F76A90054F68FBBF883A89FBB3380C21A81C`; both produce semantic digest `9346d77b4d0477a3434238924b4b63c939c098feb9f27321313de79bf28f8b54`. The corpus has 281 explicit observation rows, 6604 records, 6568 revisions, 36 absence transitions, 21 reappearances, and zero collisions independently in `observation_id`, `structure_key`, and `revision_id` namespaces.

Namespace sensitivity passed on both platforms: every observation namespace field changes `observation_id`; every structure namespace field changes `structure_key`; geometry leaves `structure_key` unchanged but changes `revision_id`. Resource limits remain passing: Windows warm `4.545 ms`, prefix `1430.523 ms`, peak `139,972,608` bytes; Linux warm `3.951 ms`, prefix `1358.796 ms`, peak `218,472,448` bytes. The validator keeps engine confirmation `unknown` and application observation `observed`; M1 remains `CLOSED_BLOCKED`, M2 false, and runtime config disabled.
