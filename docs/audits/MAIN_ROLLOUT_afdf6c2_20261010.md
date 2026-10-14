# Fixed afdf6c2 rollout — 2026-10-10 Asia/Shanghai

Owner authorized the current fixed candidate to main and production after local demo acceptance. Main was fast-forwarded to afdf6c21e7ab71d930ed52123bc260a1f36783f8 without source changes or merge conflicts. This receipt is separate documentation; deployed source stays afdf6c2.

## Identity and validation
- Source tree b248cb14346f43d59e98bad2e75cf24031ca6519.
- Immutable image sha256:1c5f59a366195a5ca54a2d9b2bf79410e376fe045fb07ad4051d4b402d728000; revision/tree labels and inventory verified independently.
- Exact source CI37473670143, workspace37473670288, audit-platforms37473670504 SUCCESS. These are GitHub results, not a new local full-suite run.
- Image artifact11418184389, ZIP395311224bytes, SHA2567901fb21bea330a71a65ef47b2c34753e7416b31c7752caba72d3a663e68b2c3; tar SHA25609180e2eb7e54b0688be6019f729876647b3c5ac7de79b9544fabbc707e738a8.
- Schema f0e1d2c3b4a5 unchanged; container strategy-file SHA256950b1b6eb3a4bdab11937f86338ab5d490fe9d94133e91f35c76ff145c9a9fd6 matches inventory. Source/config have no overriding production mounts.

## Completed deployment
- Switched2026-10-10 00:32:49 Asia/Shanghai. API/worker/scheduler all use the exact image; API/worker healthy, all three running.
- New database backup441340691bytes, gzip integrity PASS, SHA2565e5f933c51a6a96449f0e2dc6411141cf48d80a1ff1a06a348aeb491f8cdfad0. Retained old backups and efc0898 image; rollback Compose chain preserved. No migration or direct database edits.
- Owner authorized unused build-cache cleanup; actual reclaimed205.6MB. Then explicitly authorized relocating only two old transfer archives. Locally retained byte-identical copies verified against server hashes before removing the two server files. No image/container/volume/backup removal. New image streamed over SSH to avoid storing another server transfer archive. Post-load/switch disk about1.1GB free; no further cleanup.
- https://etf.joviluma.com health200/statusok. Root, Detail, OutlookPanel, indexJS/indexCSS HTTP200 and SHA256 match the CI image inventory. Initial Detail resource request had a20s network timeout; bounded retry passed, original failure retained locally.
- Anonymous /api/bootstrap401. Authenticated private reading/R10 and physical phone NOT_RUN.
- Preserved runtime provider public_composite, mockfallbackfalse, LLMfalse. Existing provider audit has news unsupported for tushare and200 records for akshare; market-context partial remains visible. No manual provider activation or data/qualification rebuild task was enqueued.
- Health APP_VERSION label remains1.0.8; source/package/frontend1.0.5. No private configuration edits to make these labels agree.

## Acceptance limits
Local fresh Python3.12 isolated demo: npm locked install/build and demo smoke PASS; desktop/390px modal open/close and support toggle PASS; no horizontal overflow. DPR2 clarity FAIL in local Chromium, label-collision specialist NOT_ACCEPTED, unequal-price switch only synthetic2:1 PASS, exact trend geometry/real corporate-action price-basis qualification NOT_RUN. Those findings were disclosed before owner authorized release; deployment is not specialist UI acceptance.

Older indicator/forecast/decision snapshots may fail current version/config compatibility until existing audited processing produces new evidence. Actual authenticated snapshot compatibility remains NOT_RUN. Real provider/license/PIT/OOS and strategy promotion remain UNKNOWN/actionable=false/not_calibrated. No broker or automatic trading enabled.

Hub revision read failed with Remote end closed connection without response; pending local report retained, no repeated send or false reporting claim.
