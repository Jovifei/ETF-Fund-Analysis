# R4C M1 OSS and engine qualification evidence — blocked

**Date:** 2026-09-28
**Scope:** evidence-only engine/dialect qualification from accepted R4B baseline.
**Accepted application baseline:** `43bfbf6929a70f520c216b759edbaa433e920e91` / `12d217af3edbe34c67bc36e75b4395ab4917b001`.
**Overall M1:** `CLOSED_BLOCKED` (`SOURCE_MAPPING_BLOCKED` for the legacy `chanlun` candidate, `CURRENT_INTEGRATION_COUNTS_ONLY`, `CAUSAL_CONFIRMATION_NOT_ESTABLISHED`, `REPAINT_CONTRACT_NOT_ESTABLISHED`, `STABLE_ID_CONTRACT_NOT_ESTABLISHED`, `RESOURCE_EVIDENCE_INCOMPLETE`).

## Scope and safety boundary

M1 did not modify runtime code, dependencies, API routes, read models, migrations, frontend structures, canonical action, Provider configuration, production data, or `actionable`. No market Provider or model call was made. `config/chan_research.json` remains disabled and is a qualification record, not a runtime enablement.

## Current integration surface

- `pyproject.toml` declares optional `chanlun>=2606.73` under the `market` extra; it does not pin an exact wheel hash or upstream commit. CZSC is not a project dependency.
- `backend/app/services/kline_stabilization_service.py` imports `chanlun` in `_chanlun_state` and exposes only counts (`fenxing`, `bi`, `segments`, `zs`). It does not serialize geometry, stable structure IDs, confirmation timestamps, repaint behavior, or a causal evidence contract.
- `backend/app/api/workbench_kline.py` calls `KlineStabilizationService.summary()` from a GET route. When `chanlun` is importable, the route loads daily bars and computes the Chan summary synchronously. Missing volume is passed to the third-party adapter as `0.0` inside this research-only path; it is not written back to `DailyBar`.
- Existing behavior is therefore an integration inventory, not a qualified R4C engine.

## Installed `chanlun` artifact

| Field | Observed value |
|---|---|
| Distribution | `chanlun` `2606.73` |
| Installed module | `E:\project\ETF-Fund-Analysis\.venv\Lib\site-packages\chanlun\__init__.py` |
| Native artifact | `_chanlun.cp313-win_amd64.pyd`, 3,622,400 bytes |
| Native artifact SHA-256 | `48cbfbc2dc28425913ac07f1b0971d296dcf6f5e3f02f1c80d994315b69597a1` |
| Metadata `License` field | absent |
| Metadata classifier | MIT License |
| Shipped license | `chanlun-2606.73.dist-info/licenses/LICENSE`, MIT, 1,067 bytes |
| Project URLs | `https://github.com/YuYuKunKun/chanlun.rs` |
| Upstream refs read | `9c972c2673a2c3e3fcbcec65de996d0c9794e873` (`main`/`HEAD`) |
| Upstream LICENSE SHA-256 | `A3359CF30C9E31DC1CB8479B9E0BBAC000B29C083FD58CCD33F08E7D702B8B24` |
| Upstream README SHA-256 | `2262B1D4BB49B37B0FAFAEA983F1CB55D13C7A9A80B3FB351618630B15AC7936` |
| Source/artifact mapping | `BLOCKED`: installed wheel/extension cannot be reproducibly tied to that upstream commit from available metadata |

The installed API exposes `K线.创建普K`, `观察者.增加原始K线`, and `分型序列`/`笔序列`/`线段序列`/`中枢序列`. The current project only consumes counts through the synchronous summary path.

## CZSC candidate

| Field | Observed value |
|---|---|
| Upstream HEAD read | `701e480a545004f945bb1721e510ae610ad90c4c` (`master`/`HEAD`) |
| Python project license | Apache-2.0 (`pyproject.toml`) |
| Rust workspace license | MIT (`Cargo.toml`, workspace version `1.0.1`) |
| Python/Rust packaging | `czsc._native` via maturin; Rust workspace under `crates/` |
| pyproject SHA-256 | `743994E92194F53BB8DA1BD03CFDA3E7ECB6408BEAE249315E3C39AD2635F024` |
| Cargo SHA-256 | `E6907E4362DE6BB3C168EEC5F3E68D4D2704885BF1CC7FFED476FDCA0364AB1C` |
| LICENSE SHA-256 | `8726741D05CB52CFF0BA8F8F8CEFFE595A53F70B7DA13B4A84E0B5B5F2AA188B` |
| Installed artifact | `NOT_INSTALLED` |
| Windows/Linux probe | `NOT_RUN_ENV` for this candidate |
| Selection | `NOT_SELECTED` |

No CZSC wheel or native artifact was installed in this stage. Upstream source metadata is not a substitute for a reproducible local artifact.

## Deterministic Windows probe

Probe script: `scripts/validate_r4c_m1.py`. It uses a frozen synthetic 300-bar alternating fixture and runs the installed `chanlun` twice plus prefixes 80/160/240/300. No network or Provider is used.

| Result | Observation |
|---|---|
| Identical full runs | Equal normalized count output: `true` |
| 300-bar counts | raw K 300; fenxing 2; bi 1; segments 0; 中枢 0 |
| Prefix 80 | raw K 80; fenxing 2; bi 1; segments 0; 中枢 0 |
| Prefix 160 | raw K 160; fenxing 2; bi 1; segments 0; 中枢 0 |
| Prefix 240 | raw K 240; fenxing 2; bi 1; segments 0; 中枢 0 |
| Prefix 300 | raw K 300; fenxing 2; bi 1; segments 0; 中枢 0 |
| Geometry evidence | `COUNTS_ONLY_NO_GEOMETRY_SERIALIZATION` |
| Causal confirmation | `NOT_ESTABLISHED` |
| Linux | `NOT_RUN_ENV` |

Stable count output is useful evidence of repeatability for this fixture. It does not qualify geometry, confirmation timestamps, repaint rules, or a dialect for M2.

## M1-R2 decision and hard stop (historical snapshot)

`config/chan_research.json` is disabled. No engine is selected. M1 stops because:

1. The installed Windows wheel lacks a reproducible wheel-to-upstream commit mapping.
2. CZSC is not installed or probed; its Python and Rust licenses/sources must be handled as separate identities.
3. Linux qualification is not available in this environment.
4. The current integration exposes counts only and performs synchronous GET computation.
5. No causal confirmation/repaint contract has been established.

M1 may resume only after exact artifacts, source mapping, licenses/NOTICE, Windows and Linux probes, geometry/capability matrix, and causal observations are independently released. M2, runtime integration, new dependencies, schema changes, Provider calls, and production changes remain unauthorized.

## Probe artifact

- Windows deterministic probe JSON: `E:\Claude_allow\Download\ETF_R4C_M1_20260928\chanlun-windows-probe.json`
- SHA-256: `000744CD69273B1549B4D822671E7034BA7ABB5D8577D424111755F8C7EEFEDA`

## M1-R1 artifact reconciliation addendum — 2026-09-28

The existing `chanlun` evidence is now partially reconciled: the cached cp313 wheel's pure-Python `chan.py` matches upstream tag `v26.6.73` commit `1477cde86bf473d708b0587c6512297ba8f5a578` byte-for-byte. The cached cp313 native wheel is not listed among PyPI 2606.73 published files, so native source/build mapping remains blocked. See [M1 artifact manifest](R4C_M1_ARTIFACT_MANIFEST_20260928.md). M1 remains `CLOSED_BLOCKED`, configuration remains disabled, and no M2/runtime action is authorized.

## M1-R3 runtime probe addendum — 2026-09-28

The exact CZSC v1.0.1 Windows and manylinux wheels were installed only in disposable environments. Normalized full/prefix/zero-volume digests matched across Windows and Linux; the probe exposed FX/BI/ZS geometry fields. Confirmation/repaint/stable-ID causality remains unqualified, so `config/chan_research.json` stays disabled and M2 is not authorized. See [R4C M1 runtime probe](R4C_M1_RUNTIME_PROBE_20260928.md).

## M1-R3.2 evidence binding — 2026-09-28

The exact recorded probe is bound to commit `f6501bd233701f7f1becfc681bc0918223898edd`, path `scripts/validate_r4c_m1_r3_czsc.py`, file SHA-256 `95B5C5A6FAB20E95312100AE0D2BE54935998B2EFD8881009455234ED924E9E2`. The synthetic fixture is code-defined in that file, so the file hash also binds the fixture and normalization logic. Existing Windows/Linux JSON hashes remain `0897890DB7BE08C198ADF1EA73CB2925D99629748D5204DB93152D138F053EE8` and `5BCB6EAF78F9C7E48FFD58820CFD5BB774C115CEB3E407F0FAD47DA83CBFD643`.

The JSON `platform` value is hard-coded to the Windows label by the historical harness and is non-authoritative for the Linux JSON; platform identity is taken from the disposable environment and wheel installation records. No probe was rerun for this documentation correction. The current configuration removes the closed `CZSC_NOT_INSTALLED` and `LINUX_PROBE_NOT_RUN_ENV` codes while retaining only active qualification blockers. M1 remains `CLOSED_BLOCKED`, M2 remains unauthorized, and production/real-data/actionability state is unchanged.
