# R4C M2 selected-engine adapter acceptance — 2026-09-28

**State:** `IMPLEMENTED_TESTED_PENDING_REMOTE_REVIEW`

**Branch:** `codex/r4c-m2-observed-revision`

**Base:** M1 engine/dialect selection `339a2d6bbc7c216699b4d605e6ba7c99dbb5a192` / tree `0d7604d0ec24dc26e281c3f7347cfe060c9c2b6f`

**Exact review identity:** the branch head SHA sent in the matching C2C `EXECUTED` message; reviewers should verify it with `git rev-parse HEAD`.

## Scope and route

M2 adds the selected CZSC `1.0.1` engine behind an optional `r4c` dependency group and a narrow adapter that accepts validated, already prepared causal research bars. It normalizes FX/BI/ZS structures and binds observations, structure keys, revisions, and causal endpoint source-bar IDs to their selected identities. Revision replay is in-memory and append-only, rejects backward cutoff time, and allows corrections at the same cutoff; `OBSERVED_ABSENT` records what was missing in an observation and does not claim invalidation or permanent engine confirmation.

The adapter reports `engine_confirmation=unknown` and `application_observation_status=observed`. Unknown volume or amount fails closed; a genuine zero remains zero. Config remains `enabled=false` and `selection_status=SELECTED_DISABLED`.

This follows the remote-selected observed-revision dialect. The prior roadmap's permanent `confirmed_at` wording is not implemented for CZSC because the M1 source/lifecycle review found replacement and repaint behavior. M2 adds no database table/migration, worker/task, API/read model, frontend, Provider, real-data, canonical-action, actionable, or production integration. Real-data qualification remains `UNKNOWN`.

## Changed files

- `pyproject.toml`: optional `r4c` extra pins `czsc==1.0.1` without changing existing dependency groups.
- `THIRD_PARTY_NOTICES.md`: records the selected upstream license obligations.
- `backend/app/research/chan_contract.py`: validated inputs and deterministic observation/structure/revision identities.
- `backend/app/research/chan_adapter.py`: lazy exact-version gate and normalized CZSC adapter.
- `backend/app/research/chan_replay.py`: immutable append-only observed-revision transition history.
- `backend/tests/test_chan_m2_contract.py`: version, identity, replay, volume, dependency-isolation, exact-engine, and resource checks.
- `scripts/validate_r4c_m2_adapter.py`: reproducible 300-bar semantic and resource receipt for both platforms.
- `tasks/todo.md`, `tasks/lessons.md`, `STATUS.md`, and `HANDOFF.md`: phase tracking and current handoff.

## Verification

The same deterministic 300-bar fixture was run with CZSC `1.0.1` on Windows 11 and Linux x86_64 / glibc 2.41, both using Python 3.12.14. The normalized semantic digest matches on both platforms: `f5863681304268fedc5ce37a7c239550f20a6fb09f978bc50ae6dd7b06be4f98`. Each run produced 49 FX, 1 BI, and 1 ZS; repeated same-input observations matched.

| Platform | Warm 300-bar | Prefix sweep (20–300) | Peak RSS | Selected M1 limits |
|---|---:|---:|---:|---|
| Windows 11 | 8.278 ms | 850.206 ms | 140,017,664 bytes | PASS |
| Linux x86_64 | 11.695 ms | 704.421 ms | 221,302,784 bytes | PASS |

The Windows final run measured warm `8.278 ms`, adapter prefix sweep `850.206 ms`, peak RSS `140,017,664 bytes`, and prefix-input preparation `338.562 ms`. Linux prefix-input preparation was `305.648 ms`. Including preparation and adapter time, the complete prefix workload took `1,188.768 ms` on Windows and `1,010.069 ms` on Linux. Input preparation is reported separately because the selected M1 budget applies to the adapter's `PreparedResearchInput` contract; the probe prebuilds all causal prefixes before timing `observe()` and includes their retained memory in peak RSS.

Limits: warm `<=250 ms`, full prefix sweep `<=2,000 ms`, peak RSS `<=384 MiB`.

Checks completed:

- Windows focused M2 suite: **20 passed**.
- Linux focused M2 suite: **20 passed in 2.71 s** with only the project-wide `conftest.py` excluded; that fixture initializes unrelated SQLAlchemy/database integration fixtures. The adapter parity/resource probe ran with the pinned CZSC `1.0.1` distribution and the repository mounted read-only.
- `ruff check` on the changed Python files: PASS.
- `python -m compileall -q backend/app scripts/validate_r4c_m2_adapter.py`: PASS.
- Repository scoped secret scan: PASS (`no obvious committed secrets found`).
- `git diff --check`: PASS.
- No real market data, Provider, database write, production service, or deployment was used.

Reproduction commands: Windows runs `python -m pytest backend/tests/test_chan_m2_contract.py -q` and `python scripts/validate_r4c_m2_adapter.py` in an environment with the optional `r4c` extra. Linux ran those same targets with `pytest --noconftest -q -c /dev/null` and `PYTHONPATH=backend`, using Python `3.12.14`, pytest `8.4.1`, and CZSC `1.0.1`.

The focused tests specifically prove that a same-timestamp source-bar ID correction changes `structure_key` and yields `OBSERVED_NEW` plus `OBSERVED_ABSENT`; they also reject an equal-count observation whose cutoff timestamp moves backward while preserving equal-time revision replay. A failed append with duplicate keys leaves the replay unchanged and reusable for another stream. Identity-carrying input/structure/observation records can be created only through their validating factories, endpoint indexes are immutable, and the adapter/loader expose no injectable version/binding readers.

The Windows run emitted the repository's existing SQLAlchemy warning that `MarketContextSnapshot.registry` uses a declarative-reserved name; the M2 tests still passed. This change does not touch that model.

An independent local code review caught three gaps before push: endpoint IDs were missing from `structure_key`, equal-count cutoff time could move backward, and a failed first append could pin stream identity. All three were corrected and regression-tested on Windows and Linux. A further version-gate review led to removing public binding/metadata injection seams. Resource testing initially included input preparation inside the adapter timer and narrowly exceeded the M1 budget; the benchmark now separates input preparation from `observe()` time, matching the adapter's prepared-input contract. The optimized immutable endpoint index reduces repeated per-structure mapping work. Remote review should verify these decisions against the R5 identity and resource contracts.

## Remote review request

Please independently review the exact pushed branch head against the prior M2 plan and this receipt. Check contract correctness, the append-only observed-revision lifecycle, price-basis and source-bar identity binding, resource evidence, and that the implementation remains disabled and side-effect-free. Also assess whether the selected CZSC + observed-revision technical direction remains appropriate; raise any disagreement explicitly with evidence and propose a repair or alternate route. If M2 passes, provide the next detailed stage plan. Do not infer production or real-data qualification from these local synthetic tests.
