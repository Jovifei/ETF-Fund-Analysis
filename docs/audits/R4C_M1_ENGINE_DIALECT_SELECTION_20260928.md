# R4C M1 engine and dialect selection review — 2026-09-28

**Decision state:** `M1_SELECTION_READINESS=READY`; runtime qualification remains `M1=CLOSED_BLOCKED` and `M2_GO=false`.
**Base:** R5.2.1 evidence tip `d82eb61f232cccd3aa1e39c53ef117ae2d968144` / tree `691cf7ba4156e2d3732ec438066c9c27d1752b35`.

## Candidate comparison

| Candidate | Provenance/platform | Lifecycle evidence | Volume/identity | Selection |
|---|---|---|---|---|
| legacy `chanlun 2606.73` | cached native cp313 build is not reproducibly mapped; no compatible published Linux Python>=3.11 artifact | counts-only integration; no causal/revision contract | unknown native provenance; no stable IDs | not selected |
| CZSC `1.0.1` | pinned upstream `90372af035f01ed9f05070eadddd265b91c84d24`; Windows wheel `18f3fb6c38f8834b8b94e35b990a9632d24e46e269bdf4d94b3aa401ce8f4581`; Linux wheel `2c65d266bd58b51960be505678f2daae69892ca4031808eeeef2ccbc2848c036`; cross-platform parity | repaint/replacement characterized; append-only observed revisions validated; native permanent confirmation unsupported | namespaced observation/structure/revision IDs, zero collisions and weak-ID checker PASS; unknown volume fail-closed | selected as disabled research candidate |

## Frozen disabled selection

- `engine_id=czsc`, `engine_version=1.0.1`, `dialect_version=r4c-observed-revision-v1`.
- `engine_confirmation=unknown`; `application_observation_status=observed`.
- Revision history is append-only observed evidence. `OBSERVED_ABSENT` is not called invalidation.
- Unknown volume remains fail-closed; no `None → 0` coercion is permitted.
- Proposed M1 resource budget: warm 300-bar `<=250 ms`, prefix sweep `<=2 s`, peak RSS `<=384 MiB`.
- `config/chan_research.json` records the selection metadata but remains `enabled=false`; no dependency, runtime, schema, API, worker, frontend, Provider, real-data, actionable, or production change is authorized.

This selection freezes a research dialect for a separate future implementation review. It does not claim immutable Chan confirmation and does not authorize M2.
