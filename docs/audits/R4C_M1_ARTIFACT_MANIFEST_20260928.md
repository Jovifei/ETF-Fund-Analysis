# R4C M1 artifact and probe manifest — 2026-09-28

**Baseline:** C2D docs `6f2c44e3f54db4ca93b10b1dafc1704ccc1d6ed1`; accepted application `43bfbf6929a70f520c216b759edbaa433e920e91` / tree `12d217af3edbe34c67bc36e75b4395ab4917b001`.
**M1 status:** `CLOSED_BLOCKED`; this manifest is evidence closure only.

## Existing chanlun artifact reconciliation

| Link | Result |
|---|---|
| Installed distribution | `chanlun==2606.73`, Windows CPython 3.13 |
| Cached wheel | `chanlun-2606.73-cp313-cp313-win_amd64.whl`, SHA-256 `3A994812AE06ABADB30DAB5AD8176B7982E28308648E81F5C21973E66359C638` |
| Wheel native member | `_chanlun.cp313-win_amd64.pyd`, SHA-256 `48cbfbc2dc28425913ac07f1b0971d296dcf6f5e3f02f1c80d994315b69597a1` |
| Wheel pure-Python member | `chanlun/chan.py`, SHA-256 `390711CEDB38AE1DC1E5209DC0854400A5E9B01BF7C1DA9E5F1CF5732D0EA377` |
| Upstream tag | `v26.6.73` → commit `1477cde86bf473d708b0587c6512297ba8f5a578` |
| Upstream `chan.py` at tag | SHA-256 `390711CEDB38AE1DC1E5209DC0854400A5E9B01BF7C1DA9E5F1CF5732D0EA377`; exact match to wheel member |
| PyPI 2606.73 published Windows artifact | cp312 wheel SHA-256 `10c5239fe5aab9dea1dd70312ff7cd0bdf392e0e2dbf2f067af81f18674e5b3b` |
| PyPI cp313 Windows artifact | not listed for 2606.73 |
| PyPI source archive | sdist SHA-256 `67061a6713483243e1d89798a7179828f3a5995e8efcd94cbed1cfc310454134` |
| Mapping result | `PARTIAL`: pure-Python source maps to the tag; the cached cp313 native build is not a published PyPI file and lacks a reproducible native-build-to-source proof |

The mapping is stronger than a package-name match but does not qualify the native artifact for M2 or runtime use. Keep `SOURCE_MAPPING_BLOCKED`.

## Candidate capability matrix

| Capability | Existing chanlun | CZSC candidate |
|---|---|---|
| Raw K construction/feeding | API present (`创建普K`, `增加原始K线`) | source metadata only; artifact not installed |
| 分型 | sequence property present; semantics not independently qualified | not probed |
| 笔 | sequence property present; semantics not independently qualified | not probed |
| 线段 | sequence property present; no geometry emitted by current integration | not probed |
| 中枢 | sequence property present; no geometry emitted by current integration | not probed |
| Stable IDs | not exposed by current integration | not probed |
| Confirmation timestamp | not established | not probed |
| Historical repaint semantics | not established | not probed |
| Incremental observer | `增加原始K线` exists; causal semantics not established | not probed |
| Backtest/signal qualification | not established by M1 | not probed |

`SOURCE_API_PRESENT`, `SOURCE_SEMANTICS_DOCUMENTED`, `RUNTIME_BEHAVIOR_PROBED`, and `QUALIFIED` are separate states. Presence of a class or sequence does not make a capability qualified.

## Cross-platform probe manifests (not executed)

- Windows executed probe: `scripts/validate_r4c_m1.py`, Python 3.13, frozen synthetic fixture, repeated normalized count output equal. Geometry and causality remain unestablished.
- Linux chanlun candidate: PyPI cp39 manylinux wheel listed with SHA-256 `66358c735ba17ebddc8e3f831dab812c2f26e60f167e3657b827207900214874`; no Linux execution in this environment. `LINUX_PROBE_NOT_RUN_ENV` remains.
- CZSC candidate: upstream ref `701e480a545004f945bb1721e510ae610ad90c4c`, Python license Apache-2.0, Rust workspace license MIT; no pinned wheel/native artifact was installed, so Windows/Linux probes are not run.
- Future probe commands must install only the exact reviewed artifact in an isolated environment, run the frozen fixture twice and prefix-by-prefix, record output digests, CPU/RSS, and native-component failure behavior. No Provider or model call is part of the probe.

## Geometry and causal probe specification

The next evidence-only probe must normalize, where the engine exposes them: `kind`, direction, start/end source-K identity, geometric bounds, engine state, native ID or derivation inputs, and confirmation timestamp. It must compare identical runs, prefix runs, appended future bars, and future-only mutations. It must distinguish first constructible, first engine-confirmed, first application-observed, and later repainted/replaced states. If the API cannot expose these fields, the capability remains `NOT_ESTABLISHED` and M1 stays blocked.

## Stop state

- `config/chan_research.json`: `enabled=false`, no engine selected.
- M1: `CLOSED_BLOCKED`.
- M2, runtime integration, dependency installation, schema/API/frontend changes, Provider calls, real-data qualification, canonical-action changes and production changes: not authorized.

## M1-R2 artifact ABI and source-semantic closure — 2026-09-28

### Chanlun 2606.73 published artifact matrix

| Artifact | Published SHA-256 | Compatibility with this project |
|---|---|---|
| `cp312-cp312-win_amd64.whl` | `10c5239fe5aab9dea1dd70312ff7cd0bdf392e0e2dbf2f067af81f18674e5b3b` | usable only for Python 3.12; current probe runtime is 3.13 |
| `cp39-cp39-manylinux_2_17_x86_64` | `66358c735ba17ebddc8e3f831dab812c2f26e60f167e3657b827207900214874` | incompatible with the project minimum Python 3.11 runtime |
| `cp312` macOS wheels | published | not a target platform for this Windows/Linux application |
| `cp313-cp313-win_amd64` cached wheel | `3A994812AE06ABADB30DAB5AD8176B7982E28308648E81F5C21973E66359C638` | not listed in PyPI 2606.73 release files; native provenance remains blocked |
| sdist | `67061a6713483243e1d89798a7179828f3a5995e8efcd94cbed1cfc310454134` | building it would be a new installation/build action, not performed in M1 |

### Pinned CZSC release candidate (metadata only)

- Release: `v1.0.1`.
- Upstream commit: `90372af035f01ed9f05070eadddd265b91c84d24`.
- Python project license: Apache-2.0; Rust workspace license: MIT.
- Published `cp310-abi3-win_amd64` wheel SHA-256: `18f3fb6c38f8834b8b94e35b990a9632d24e46e269bdf4d94b3aa401ce8f4581`.
- Published `cp310-abi3-manylinux_2_17_x86_64` wheel SHA-256: `2c65d266bd58b51960be505678f2daae69892ca4031808eeeef2ccbc2848c036`.
- Published sdist SHA-256: `30b4257f3bfa936c420b144c3115ad1ca95f013ce11d8389974114f57b9de50e`.
- No artifact was installed or executed. No dependency declaration changed.

### Source-level semantic inventory (no runtime qualification)

- Existing chanlun stubs expose `观察者.分型序列`, `笔序列`, `线段序列`, `中枢序列`, `增加原始K线`, and `静态重新分析`; the current adapter does not expose object geometry, source-K identities, stable IDs, or confirmation/repaint timestamps.
- CZSC v1.0.1 stubs expose `CZSC.fx_list`, `bi_list`, `zs_list`, `update`, `from_dataframe`, `BI.fx_a/fx_b/bars`, `FX.new_bars/raw_bars`, `ZS.bis`, and `get_zs_seq`. These establish source API presence only. The reviewed stubs do not by themselves establish the project's causal confirmation timestamp, stable revision identity, or repaint contract.
- Both candidates therefore remain `SOURCE_API_PRESENT` in parts and `QUALIFIED=false`; M1 remains `CLOSED_BLOCKED`.

### M1-R2 stop

No installation, Linux/container execution, runtime integration, Provider call, schema/API/frontend change, M2 implementation, canonical-action change, actionable change, or production change is authorized by this evidence-only slice.
