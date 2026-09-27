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
- causal prefix-sweep wall time and serialized output size.

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

## Pinned source lifecycle findings

The implementation review is bound to CZSC source commit `90372af035f01ed9f05070eadddd265b91c84d24` and the following source blobs downloaded from that commit:

| Source | SHA-256 | Findings |
|---|---|---|
| `crates/czsc-core/src/analyze/mod.rs` | `CD6665045961FB485E8E04D00E4DA9B3CC7EDE22AD46435BE5270BEBE1CF00EF` | `new` feeds every bar through `update_bar`; same-`dt` bars replace the current bar; `__update_bi` can pop a broken last BI; `finished_bis` drops the last BI when `bars_ubi.len() < 5`; `zs_list` is recomputed from finished BIs; history is pruned. |
| `crates/czsc-core/src/analyze/utils.rs` | `D9245CBC6D70CD140077A73105F65FA630DF93DDAE5F0C0A9B2DA31616ED56E1` | FX uses a three-NewBar window; BI selects later opposite FX and requires `bars_a.len() >= min_bi_len`; ZS is rebuilt by popping/merging the current last ZS; inclusion merges can retain one ID and truncate element provenance. |
| `crates/czsc-core/src/objects/fx.rs` | `A1BD56921E6151C55AA0946D2CBE8D76DDAD595FF6DE56EE3E71820E119A44F4` | FX has `dt/mark/high/low/elements`, but no confirmation, revision, or stable ID. |
| `crates/czsc-core/src/objects/bi.rs` | `824FD03C8BE86AE80085DB84242815AC222B9D1B46BA397744DFFBBA3F4CB315` | BI has `fx_a/fx_b/fxs/direction/bars`; source endpoints are derived from FX elements; no confirmation or stable ID. |
| `crates/czsc-core/src/objects/zs.rs` | `CF63B3434C410C5A7BCB7243C8DE4637B826D5933F29E7013F374B12EA006E98` | ZS has BI list, interval and bounds, but no persistent identity or confirmation state. |
| `crates/czsc-core/src/objects/bar.rs` | `5462A555BEBDEDE6B7ABDC4D1F3B8C0F879700927A808A362A90066D55E4EA77` | `RawBar.vol` and `amount` are mandatory `f64`; an unknown volume cannot enter the native constructor. |

The exact lifecycle locations are `analyze/mod.rs:178-235, 241-314, 524-534, 684-685`, `analyze/utils.rs:31-50, 177-242, 264-443`, `objects/fx.rs:37-194`, `objects/bi.rs:33-161, 308-315`, `objects/zs.rs:21-107`, and `objects/bar.rs:34-108`. No source field or test establishes a permanent engine confirmation timestamp, repaint-free revision, or native stable ID.

## R4 execution receipt

The final committed methodology is `9de3b2679c3c07810688560411b91392db34b3b9`, tree `df1f289b9dbd5ab237cd8ac5f77f4d4f83a5e837`, with probe file SHA-256 `108FE8AA3B156363555AB43D5993707422B331C487B26FFAD6E97A8F9C5DD7CF`. The exact pinned wheels were hash-verified before each disposable run:

- Windows cp310-abi3 wheel: `18F3FB6C38F8834B8B94E35B990A9632D24E46E269BDF4D94B3AA401CE8F4581`.
- Linux manylinux x86_64 wheel: `2C65D266BD58B51960BE505678F2DAAE69892CA4031808EEEEF2CCBC2848C036`.

Final output bindings:

| Environment | JSON SHA-256 | Semantic digest | Prefix ledger digest | Final counts |
|---|---|---|---|---|
| Windows CPython 3.12 | `49C7A99530438FBFA5369BA6C51E475E28FF9B3E1FE27F4BE99B5A7EDAA02B60` | `7be7357d6135b4822bb8f2fd3e6db3e08572dd2781d583355293502df169a4cb` | `24d17f84d5d3bf01059e9affb72dde0a24cbad7be939eba8fd526383cf106adc` | 49 FX / 1 BI / 1 ZS |
| Linux Python 3.12 | `FD6E067904FEC335B7FC065372C5E39AAB8FDD359CF4482F63CA9F5245BC395D` | same | same | 49 FX / 1 BI / 1 ZS |

The semantic and prefix digests match across platforms. Platform metadata is kept outside those digests. The prefix ledger contains explicit `prefix_end_bar_id`; a 20-bar prefix records `2026-01-20T00:00:00#0019`.

Resource measurements were recorded in both environments: Windows cold import `894.260 ms`, warm full run `4.618 ms`, full prefix sweep `1,134.520 ms`, peak working set `138,428,416` bytes, output `7,443,352` bytes; Linux cold import `451.103 ms`, warm full run `3.973 ms`, full prefix sweep `996.280 ms`, peak `VmHWM` `218,566,656` bytes, output `7,443,286` bytes. These are measurements, not an adopted production budget; independent review must decide whether and how they become a gate.

Volume semantics remain explicit: positive and true-zero inputs produce the same normalized digest `9cc896bbe195c04ecbbb72904c86ab5b0990c28594e1030883bfe0f1dc7cf8f6`; unknown volume fails at the native constructor with `TypeError: argument 'vol': must be real number, not NoneType`. No unknown value was coerced to zero.

Future-only suffix results are not a qualification pass. With cutoffs 80/160/240, normal suffixes removed 1/1/2 prior candidate identities and added 1/1/1; mutating only bars after the cutoff removed 6/22/39 prior identities. No same candidate identity was classified as merely changed. This is direct evidence that the current engine can rebuild or remove earlier structures when later bars arrive; it does not establish a repaint-safe or permanent confirmation contract.

**R4 result:** `M1=CLOSED_BLOCKED`. The config remains disabled and engine-less. Causal confirmation, repaint/replacement, stable identity, and a reviewed resource budget remain open; no M2, runtime integration, dependency, Provider, real-data, canonical-action, actionable, or production change was made.
