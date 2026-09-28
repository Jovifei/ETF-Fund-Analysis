# R4C M2 selected-engine adapter acceptance — 2026-09-28

**State:** `M2_R1_IMPLEMENTED_TESTED_PENDING_REMOTE_RE_REVIEW`

**Branch:** `codex/r4c-m2-observed-revision`

**Base:** M1 engine/dialect selection `339a2d6bbc7c216699b4d605e6ba7c99dbb5a192` / tree `0d7604d0ec24dc26e281c3f7347cfe060c9c2b6f`

**Exact review identity:** the R1 branch head SHA sent in the matching C2C `EXECUTED` message; reviewers should verify it with `git rev-parse HEAD`. Initial M2 commit `ac8e3ea3fc251d74c7d88e82550ae88cfb3d14ff` remains unchanged; iteration 56 returned `M2=CHANGES_REQUIRED` and retained route A.

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
- `config/chan_research.json`: replaces stale M1 blocker codes while remaining disabled and blocked.
- `scripts/validate_r4c_m2_adapter.py`: reproducible 300-bar semantic and resource receipt for both platforms.
- `tasks/todo.md`, `tasks/lessons.md`, `STATUS.md`, and `HANDOFF.md`: phase tracking and current handoff.

## Verification

The same deterministic 300-bar fixture was run with CZSC `1.0.1` on Windows 11 and Linux x86_64 / glibc 2.41, both using Python 3.12.14. The normalized semantic digest matches on both platforms: `091254d34ddfeeadc85cd0b17e035295bfc32f8a0cebc6776440f10be82aaeac`. Each run produced 49 FX, 1 BI, and 1 ZS; repeated same-input observations matched.

| Platform | Warm 300-bar | Prefix sweep (20–300) | Peak RSS | Selected M1 limits |
|---|---:|---:|---:|---|
| Windows 11 | 8.478 ms | 1,030.229 ms | 139,882,496 bytes | PASS |
| Linux x86_64 | 9.807 ms | 750.328 ms | 219,942,912 bytes | PASS |

The Windows final run measured prefix-input preparation `402.526 ms` and combined preparation + adapter time `1,432.755 ms`; Linux measured `371.528 ms` and `1,121.856 ms`. The probe prebuilds all causal prefixes before timing `observe()` and includes their retained memory in peak RSS.

Limits: warm `<=250 ms`, full prefix sweep `<=2,000 ms`, peak RSS `<=384 MiB`.

Checks completed:

- Windows focused M2-R1 suite: **25 passed**.
- Linux focused M2-R1 suite: **25 passed in 3.11 s** with only the project-wide `conftest.py` excluded; that fixture initializes unrelated SQLAlchemy/database integration fixtures. The adapter parity/resource probe ran with the pinned CZSC `1.0.1` distribution and the repository mounted read-only.
- R5.2.1 identity/collision validator: Windows and Linux both report zero collisions in all three namespaces, `collision_checker_self_test={"collision_count":1,"detected":true}`, and the same semantic history digest `0f4ae0322b5d390c41e618da4c342abea66baac30bce4ccfe4a5f0d713cff76f`. The first Windows run shared CPU with another verifier and measured 2,046.457 ms; the sequential rerun passed at 1,949.954 ms. Linux passed at 1,633.037 ms.
- `ruff check` on the changed Python files: PASS.
- `python -m compileall -q backend/app scripts/validate_r4c_m2_adapter.py`: PASS.
- Repository scoped secret scan: PASS (`no obvious committed secrets found`).
- `git diff --check`: PASS.
- No real market data, Provider, database write, production service, or deployment was used.

Reproduction commands: Windows runs `python -m pytest backend/tests/test_chan_m2_contract.py -q`, `python scripts/validate_r4c_m2_adapter.py`, and `python scripts/validate_r4c_m1_r5_revision_ids.py` in an environment with the optional `r4c` extra. Linux ran the focused suite with `pytest --noconftest -q -c /dev/null`, plus both validators under `PYTHONPATH=backend`, using Python `3.12.14`, pytest `8.4.1`, and CZSC `1.0.1`.

The focused tests specifically prove that a same-timestamp source-bar ID correction changes `structure_key` and yields `OBSERVED_NEW` plus `OBSERVED_ABSENT`; they also reject an equal-count observation whose cutoff timestamp moves backward while preserving equal-time revision replay. Same-ID identical observations are idempotent; same-ID conflicting structures fail atomically. Observation factories reject duplicate keys and canonicalize structure ordering. Replay rejects config/engine/dialect/adjustment namespace changes while allowing ordinary input revision and settlement changes. Identity-carrying input/structure/observation records can be created only through their validating factories, endpoint indexes are immutable, and the adapter/loader expose no injectable version/binding readers.

The Windows run emitted the repository's existing SQLAlchemy warning that `MarketContextSnapshot.registry` uses a declarative-reserved name; the M2 tests still passed. This change does not touch that model.

Iteration 56 found two new replay-integrity blockers and three stale disabled-config reason codes. M2-R1 corrects them without changing the selected route or R5 identity formulas: observation factories reject duplicate keys and sort structures, replay distinguishes identical idempotent retries from same-ID conflicts, the stream namespace includes adjustment/config/engine/dialect identities, and config reasons now describe disabled integration/persistence/read-model work. Qualification remains `BLOCKED`; runtime remains disabled. Remote review should verify these fixes against the R5 identity contract.

An independent local R1 review found no remaining actionable issue and confirmed the R5 identity formulas are unchanged.

## Remote review request

Please re-review the exact pushed R1 branch head against the iteration-57 repair plan and this receipt. Verify same-ID conflict behavior, canonical structure ordering, config/engine/dialect/adjustment stream isolation, the R5.2.1 collision regression, resource assertions, and disabled scope. Route A was retained in iteration 56; state any remaining disagreement with evidence. Decide M2 PASS or CHANGES_REQUIRED. Only if M2 passes, provide the detailed M3 plan; do not infer production or real-data qualification from synthetic tests.
