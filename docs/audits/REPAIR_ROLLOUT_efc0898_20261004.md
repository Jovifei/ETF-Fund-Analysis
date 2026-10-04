# Frozen chart/algorithm release — 2026-10-04

Remote author/reviewer recommended deployment of efc0898dd13d386b8b4d91854323e36ceffa0630. Local performed acceptance and rollout only; business/test changes came from remote GitHub commits.

## Release identity and checks

- Source tree4a526501991a683fba0249c3d4ede33fd5308533; immutable image sha256:e01a951d8510346ade109d45167edb9c42bf201063d00de84bb3f13df74b8bd7.
- Exact fullCI37185841440,workspace37185841412,platform37185841426 SUCCESS. Full unit/integration,image build/smoke/inventory/export passed.
- Local affected57PASS, source-equivalent Vue172PASS,responsive16PASS,modal6PASS,fractal/projection3PASS,typecheck/build/compileall/Node11PASS. Earlier full failure and subsequent corrections remain in reception receipts; no invented new full local run.
- Artifact11297069028 ZIP398149523bytes SHA25639e72a62c224778c87435f506afb37f218ee6b2b6e89593138f3424a5483fc70; tarSHA2569fdb3d1b4d7b09b29e98ced7116772776e7242aad7b7f21e8e35363d555e0f03. Docker config hash/revision/tree independently match inventory; version1.0.5/frontend1.0.5/schemaf0e1d2c3b4a5. Registry digest remains absent for CI-exported image, not falsely claimed published.

## Actual rollout

- Completed2026-10-04T08:07:05Z =16:07:05 Asia/Shanghai. API/worker/scheduler all running exact new image; API/worker healthy; schema unchangedf0e1d2c3b4a5.
- Fresh backup `/opt/china-fund-decision/release-repair-efc0898/backup/fund_decision_20261004_154850_HKABUn.sql.gz`,355614173bytes,gzipPASS,SHA256f43aac5c443b5b2bbe25b51628de7a861206fb80195aec3451e42cb0ce97fd0e.
- Original image4c270b421d74748717ea16fe2ad1d69b7e93d27cbdcd69eae6695f0b77a76835 and previous eight-compose-input chain retained. New final override `/opt/china-fund-decision/release-repair-efc0898/candidate.yml`; controlled switch script contains health/source/schema gates and rollback.
- First transfer corrupted because a concurrent verification re-extracted the uploading archive. Load failed before service switch; old services remained running. Corrupt artifact retained; stable archive retransferred and remote hash/gzip/source verification passed before successful load/switch. This operational failure is not erased.
- https://etf.joviluma.com health200/statusok; root,Detail,OutlookPanel,indexJS/indexCSS all200 and SHA256 match exact image inventory. `/api/bootstrap` anonymously401. Authenticated-private and physical-phone acceptance NOT_RUN.
- Existing scheduler subsequently recorded refresh_decision_board succeeded,generate_report succeeded,refresh_market_context partial. Provider audits include akshare context/breadth ok and tushare news unsupported; no raw sensitive logs copied. Local did not enqueue data rebuilding/qualification tasks.

## Boundaries and next remote review

- Image-only rollout preserved runtime overrides. Health reports version1.0.8 although source/inventory version1.0.5; observed provider public_composite,allow_mock_fallbackfalse,llm_enabledfalse. No `.env` read/echo/change. Remote must assess the version-label/provider configuration drift against current contract without silently promoting qualification.
- Real provider/license/PIT/calibration remains UNKNOWN/actionable=false/not_calibrated; service health and synthetic correctness do not qualify investment forecasts.
- Server3.2Gavailable/92%used after preserving backup/corrupt-transfer evidence; no unrelated cleanup or network changes performed.
- Release branch remains frozenefc0898. Remote independently delivered next-stage branchcodex/post-release-indicator-audit-20261004@b945ad8fb52d4ffa725c4ccb23fbdae5f3097141; receive/test separately after this rollout receipt is reviewed, never fold it into this release silently.
