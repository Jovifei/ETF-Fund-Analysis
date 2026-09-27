# R4C M1-R3 isolated CZSC runtime probe — 2026-09-28

**Baseline:** M1-R2 commit `569c66a524a101e1eaa53c5432c6d5829e3221fb`, tree `69ac5a0fe8b03357ef8277c36a92f38c8c1b6ff7`.
**Candidate artifact:** CZSC `v1.0.1`, upstream `90372af035f01ed9f05070eadddd265b91c84d24`.
**Scope:** disposable Windows and Linux environments only; no project dependency, Provider, model, API, frontend, schema or production change.

## Exact artifacts and environments

| Environment | Artifact | SHA-256 | Result |
|---|---|---|---|
| Windows CPython 3.12, cp310-abi3 | `czsc-1.0.1-cp310-abi3-win_amd64.whl` | `18f3fb6c38f8834b8b94e35b990a9632d24e46e269bdf4d94b3aa401ce8f4581` | installed only in disposable `win-venv` |
| Linux Python 3.12, manylinux x86_64 | `czsc-1.0.1-cp310-abi3-manylinux_2_17_x86_64.manylinux2014_x86_64.whl` | `2c65d266bd58b51960be505678f2daae69892ca4031808eeeef2ccbc2848c036` | installed only in disposable Docker container |

The first Linux dependency download timed out; the same exact wheel was retried with a bounded timeout and the complete dependency environment installed. The initial failure and retry log remain outside the repository. Both disposable environments were removed/left outside the project tree after probing.

## Normalized probe

Probe: `scripts/validate_r4c_m1_r3_czsc.py`; frozen synthetic 300-bar alternating fixture, full repeated run, prefixes 80/160/240/300, and volume zero comparison. No market data or Provider call.

- Windows probe JSON SHA-256: `0897890DB7BE08C198ADF1EA73CB2925D99629748D5204DB93152D138F053EE8`.
- Linux probe JSON SHA-256: `5BCB6EAF78F9C7E48FFD58820CFD5BB774C115CEB3E407F0FAD47DA83CBFD643`.
- Full normalized digest: equal on Windows/Linux.
- Prefix digests: equal on Windows/Linux for 80/160/240/300.
- Zero-volume normalized digest: equal on Windows/Linux.
- Full normalized counts: 49 FX, 1 BI, 1 ZS on both platforms.
- Geometry fields extracted: FX `dt/mark/high/low`; BI `sdt/edt/direction/high/low`; ZS `sdt/edt/zg/zd`.
- Windows warm probe wall time: approximately 970 ms. Peak RSS and Linux wall/RSS were not measured in this run.

## Interpretation

This closes artifact import and cross-platform normalized-output probes for the pinned CZSC candidate. It does not establish application qualification: confirmation time, repaint/replacement behavior, stable IDs, future-only mutation behavior and source-K causal observation still require an explicit ledger. `config/chan_research.json` remains `enabled=false`, no engine is selected, and M2/runtime integration remains forbidden until independent review.
