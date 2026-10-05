# Classification evidence content identity — 2026-10-05

## Local candidate and dependency

This is a **local-only candidate** based on local commit `d9d1dea9734f2a52c865a44d2d8b6c1b418ad67e` (tree `360f2f88fb353c382b31f3233f3593877cd7bcf7`). That current-board stage is not yet published. The last published original-branch commit remains `6608602093d27704b4bebc8fb2affe36f65cfc32`, whose three exact workflows succeeded. This candidate must not be represented as tested directly on remote `6608602` or published without its dependency.

No remote write, deployment, data refresh, provider activation, purchase or investment transaction is performed for this stage.

## Confirmed evidence gaps

1. The original historical-classification contract contained policy/flags and instrument count but no instrument identities or labels. Equal-sized collections with different instrument codes or theme labels therefore produced the same contract hash.
2. Workspace factor-report reads authenticated the whole report and checked research/universe evidence, but did not validate or bind classification evidence. Missing, mismatched or falsely qualified classification contracts could still be labelled current.
3. Global-model research required merely a nonempty classification version; second-engine replay checked only the version string. Neither proved that actual classification rows were present.

The initial new regression set reproduced eight failures and one positive pass. A further two source/projection-policy negative cases failed before adding their explicit checks. These are evidence-contract failures, not changes to factor mathematics or proof of investment performance.

## Bound current-label snapshot

`historical-classification-v2-content-bound` records a deterministic mapping from exact instrument code to `theme_l1` and `theme_l2`, preserving unknown labels as null. The mapping covers the queried source instrument collection; exclusions from downstream research are still separately recorded by the existing data contracts.

- Input order does not change the contract hash.
- Instrument code or either label changing does change the contract hash.
- Duplicate, missing or invalid instrument identity is rejected instead of silently collapsing a row.
- The contract validator requires its source/projection policy, exact integer count, label-row shape and explicit current-label/non-PIT qualification flags.
- Existing flags remain: historical membership unavailable, theme PIT false, historical theme backtest constraint false, qualification UNKNOWN.

This is a recorded current-metadata snapshot. It does not create effective-dated historical classifications, reconstruct delisted constituents, or qualify a historical theme constraint.

## Readers

- Factor current-read requires a valid v2 classification contract and an exact match with persisted `classification_contract_hash` metadata. Missing/malformed/mismatched evidence becomes incompatible and no report is returned as current.
- Global-model research validates the full classification contract before model training.
- The independent crosscheck validates the same evidence contract before replay; its execution/replay algorithms remain independent.
- Current positive report/panel test fixtures now use the real contract builder rather than a partial handcrafted version string. Explicit negative cases retain missing, wrong-version, wrong-hash, count, label, source, policy and false-PIT mutations.

## Version and semantic boundary

Metadata identities advance to:

- `factor-analysis-v0.2.4-classification-evidence`
- `global-model-research-v0.2.4-classification-evidence`
- `rotation-v0.5.7-classification-evidence`

No numeric feature, factor formula, training split, predictor, historical selection, commission, slippage or execution rule changes. Reports/snapshots with prior identity/config hashes remain historical rather than being relabelled current. No automatic recomputation or live qualification promotion is performed.

## Verification

The initial correction passed 18 focused cases. After source/policy, malformed-label/count, duplicate identity and crosscheck negatives, 24 focused cases passed. Extended primary/crosscheck/backtest and complete backend runs are in progress against the frozen local candidate; independent review is pending. Earlier local/full and hosted results do not substitute for these new runs.

Real-data qualification remains UNKNOWN, actionable=false and calibration_status=not_calibrated. Current artifact compatibility is not a claim that its data is fresh, historically PIT-qualified or profitable.

## Independent review correction: bind the consumer's identities

Review identified a further real gap before acceptance: a contract could be internally well-formed but belong to an empty or different instrument collection. Five additional regressions reproduced this across factor current-read, global-model input and crosscheck.

The shared validator now takes explicit expected codes at every consumer:

- Factor current-read and crosscheck require exact agreement with the persisted universe's `instrument_codes`.
- Global-model research requires every actual panel code to be covered. Extra captured source-universe codes are allowed only on this explicit subset route because the factor panel can exclude source instruments for data quality.
- Missing, invalid or duplicate expected-code context is rejected. A truly empty classification collection is valid only where the consumer is also empty; it cannot cover a nonempty panel/universe.

The updated focused set passed 30/30. The earlier full run was intentionally interrupted (exit 130, around 16%) after the review found this gap; it is not a pass. New expanded and complete runs use the corrected frozen candidate.

## Corrected candidate review and expanded regression

Independent final review PASS: the original consumer-coverage gap is closed; source hashes match the frozen candidate; formulas, model training and selection logic remain unchanged. Reviewer independently reran the new classification and report-artifact modules: 24/24 passed. The 30/30 focused and 45/45 expanded JUnit reports were independently inspected; both contain zero failures/errors/skips. Expanded coverage includes the primary transaction backtest, independent crosscheck and global-model walk-forward.

Frozen SHA-256 identities:

- historical_classification_contract.py: `305165d241094d156ecf43b6c6fc530ff986b6444d8705ee29d9eb946ea960c3`
- crosscheck_engine.py: `62e02fda6dbac6ae0161ad4a2f8d1ab18aec77f4b88a61704ec4b64319c76bf4`
- global_model_research_service.py: `9a36950f2a0462c57f0c09b20df5fcb18b34212daa94e1c0da338669bad4307c`
- workspace/read_model.py: `20b9407e3d86377d558ddaabda2b8be77a20b7ffbe4ededa6d3fcbfe39aa8f32`
- test_classification_evidence_identity.py: `9fe32309bb502633cbcf860ec3a0b07f67cedf690a5edcd23e8fcdf6eb18f90b`
- test_report_artifact_contract.py: `1b92293ae792a34841c9f5e3a5f1ca73c89aa59cf420b71d069b3d0b7f27a4d9`
- test_global_model_walk_forward.py: `6bc8b8e8088648591b46cff6bae097b38ef2df115707ed410de45501a8a07e82`
- strategy.json: `950b1b6eb3a4bdab11937f86338ab5d490fe9d94133e91f35c76ff145c9a9fd6`

New contract/test modules pass the configured Ruff checks; affected legacy consumers pass critical Ruff checks. Python compilation, legacy app JavaScript syntax and diff checks pass. Full-suite terminal status remains pending and remote publication has not been attempted for this stage.

## Final local complete regression

Frozen corrected candidate: **1,773 collected, 1,762 passed, 11 existing optional/platform skips, 0 failures/errors**, 938.848 seconds. JUnit SHA-256: `bb824269154f4ad888388a4b9ffef41d41fa5acd01731ad1076efdab8c69a50a`.

Expanded 45/45 JUnit SHA-256: `3276233c979d194cd4a0915b5bfa3ff796db6410cdbf3a25fc255909d77d6a21`. Independent 24/24 JUnit SHA-256: `f7c499a5f99c12eaffe37e985b508c2361392f3ff2f989987ccc27bff560bb6f`. All eight reviewed source/test/config hashes remain unchanged.

This closes local implementation/review/testing only. No remote tree/ref update has been attempted for this candidate, and there is no exact-commit hosted CI or deployment receipt. The unpublished current-board parent remains an explicit dependency. Publication must be resumed through the authorized original-branch process after the existing execution restriction is resolved; it must not be bypassed or bundled into an unrelated write.
