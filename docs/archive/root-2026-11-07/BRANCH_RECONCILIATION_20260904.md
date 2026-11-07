# 远端分支最终收口审计（2026-09-04）

本文件记录 2026-09-04 对 `Jovifei/ETF-Fund-Analysis` 远端历史分支的最终处置。判断标准不是 Git Graph 是否仍显示分叉，而是功能是否已经进入当前 `main`、是否被后续实现取代，以及旧分支是否包含与最终产品合同冲突的语义。

## 最终产品合同

1. 用户只使用 `/` 统一 ETF 决策界面；旧 `/legacy`、`/workbench/1430`、`/workbench/kline` 及旧静态 HTML 入口只允许重定向到 `/`。
2. 当前 ETF 五档只能有一套：`DecisionBoardSnapshot -> SignalGradeService -> SignalSnapshot last-resort audit`。
3. `bear_cont` 不得因为“持续空头”这一显示状态自动升级成“减仓”；真正减仓仍由 KDJ 死叉、MACD death/approach_death 等当前合同触发。
4. Forecast 研究期限统一为 1/3/5/10；未校准 `p_up` 只表示历史相似样本上涨频率。
5. 14:30 provisional OHLCV 可用于当前指标/分级/支撑压力，但在没有同一时点历史盘中样本前不得与历史 EOD 邻居混算未来收益预测。
6. 生产数据源、时间戳资格、scheduler、认证、备份和 Docker 安全边界以当前 `main` 为准。

## 已经通过 PR / squash merge 吸收到 main 的功能

以下分支虽然 Git 历史可能因 squash merge 看起来与 main 分叉，但功能已经通过 PR 验证后进入主线，不应再次 merge/cherry-pick：

- `feat/workbuddy-decision-board-replica-v2` -> PR #2
- `feat/unified-etf-decision-row-board` -> PR #3
- `fix/reference-board-signal-consistency-v2` -> PR #4/#6 后续冲突收口
- `feat/oss-purged-validation-20260903` -> PR #6
- `fix/signal-grade-pct-units-20260903` -> PR #8
- `feat/horizon-alignment-13510-20260903` -> PR #10
- `feat/canonical-current-decision-20260903` -> PR #11
- `feat/purged-expanding-walkforward-20260903` -> PR #12
- `fix/confidence-ignore-copy-20260903` -> PR #13
- `fix/runtime-truth-ops-hardening-20260903` -> PR #14
- `fix/scheduler-production-resilience-20260903` -> PR #15
- `fix/composite-provider-per-code-coverage-20260903` -> PR #16
- `research/oss-factor-diagnostics-20260903` -> PR #17
- `fix/single-etf-decision-surface-20260903` -> PR #18
- `fix/horizon-fallback-contract-20260903` -> PR #19（已清理远端分支）
- `fix/provisional-forecast-time-basis-20260903` -> PR #20（已清理远端分支）

## 已被当前 main 完整包含的旧分支

以下分支相对当前 main 为纯 `behind`，没有 main 缺失的文件差异，可以安全清理：

- `codex/ftshare-demo-integration`
- `codex/multi-model-market-context-ocr`
- `codex/multi-user-auth`
- `feat/etf-1430-workbench-complete-local`
- `feat/screenshot-signal-board`
- `feat/signal-center`
- `feat/v070-qualification`
- `feat/workbuddy-decision-board-replica`
- `fix-akshare-sector-kline-fallback`
- `fix-ci-market-context-tests`
- `fix-docker-egginfo-ci-smoke`
- `integration/all-features-20260902`
- `integration/all-features-20260902-v4`
- 多个早期 `fix/reference-board-parity-*` stage/v1/v2/work/backup 分支

## 不应直接合并的历史/临时分支

### `codex/source-export`

独有内容主要是 `.automation/v070/*` 的旧源码快照和一次性 workflow；PR #6 已明确记录“不合并 source-export”。这些不是生产功能。

### `integration/all-features-20260902-v2` / `v3`

相对 main 的独有内容只有临时 integration workflow，不属于产品代码。

### `feat/etf-1430-forecast-workbench`

相对 main 的独有内容仅有 direct-write probe / status 文档，不是产品能力。

### `feat/screenshot-signal-board-v2`

这是旧的独立 screenshot signal-board 页面与大量一次性 automation/workflow。其行业/概念 ETF 代理能力已经由当前 `BoardService + board_catalog.json + SectorSnapshot/sector taxonomy` 体系取代；恢复该分支会重新引入第二套页面。

### `feat/reference-v4-decision-board`

PR #5 已明确标为 superseded；后续统一页面和 canonical decision 合同已经取代它。

### `fix/reference-board-parity-final-safe`

PR #7 已明确标为 superseded。该分支含有被最终合同拒绝的 `bear_cont -> 减仓` 语义，因此不得整体合并。

### `feat/reference-v4-final-parity`

该分支没有作为最终 PR 整体合入。审计后只有少量“显示层”契约值得保留：

- MACD gold 的强势/弱势金叉显示；
- bull continuation 在 DIF <= 0 时显示为修复延续；
- RSI 70/50/30 四档文字口径；
- 参考页文档语义。

这些安全内容已经在本次 reconciliation 分支上重新实现并加测试；旧分支本身仍不直接 merge，以避免把旧 UI、旧页面职责或冲突语义带回主线。

## 本次额外修复

- `docs/PRIVATE_REMOTE_DEPLOYMENT.md` 加入仓库 `.gitignore`。私有部署手册本身保持纯本地，不上传 GitHub。
- 修正文档中仍把 `/legacy` 描述为独立完整系统的陈旧说明；当前合同是全部历史页面入口重定向到统一 `/`。
- SignalGrade 显示版本升级为 `signal-grade-v0.3.1-reference-display`。
- RSI 显示分层统一为：`>=70` 超买、`50~70` 正常偏强、`30~50` 偏弱、`<30` 超卖。
- MACD 显示增强不改变 `kind`；特别锁定 `bear_cont` 仍不是自动减仓条件。

## 清理原则

本 reconciliation PR 合并并通过最终 main CI 后，可删除上述已经被吸收、纯 behind、superseded 或只有临时 automation 的远端历史分支。删除分支只是清理 ref，不改变已经进入 main 的文件内容。以后所有新功能都从最新 `main` 新建短生命周期 feature branch，通过 PR + CI 合入后立即删除 feature branch。
