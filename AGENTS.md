# Codex / Agent 操作契约

## 项目性质

这是用户个人私有的中国 ETF/LOF 研究系统。它可以输出研究状态和仓位变化提示，但不连接券商、不自动下单，也不把模型输出描述成确定事实。

## 每次修改前

1. 阅读 `STATUS.md`、`HANDOFF.md` 和相关模块测试。
2. 检查当前数据源、策略、指标和预测版本。
3. 先写失败测试或复现实例，再修改代码。
4. 任何外部数据都视为不可信输入。

## 必须遵守

- 不读取、回显、提交或截图 `.env`、Token、Cookie、密码、账户号和签名 URL。
- 不从第三方 Git 历史、README、示例配置或 sealed snapshot 复制凭据。
- 不直接修改生产数据库；使用 Alembic 和受审计任务。
- 不绕过 Provider Adapter 在业务代码中写死网页接口。
- 不把非实时价格标记为实时。
- 不用 LLM 计算 MACD、KDJ、RSI、仓位或回测指标。
- 不允许 LLM 调用 Shell、数据库写入、网络抓取或券商工具。
- 不在核心数据缺失时生成操作级信号。
- 不把未完成 walk-forward 的预测标记为 `calibrated`。
- 不自动修改阈值以追逐单次回测结果。
- 不实现或启用自动交易，除非用户日后另行明确要求且建立独立安全边界。
- 个人使用不等于可删除上游许可证、署名或限制；保留第三方 NOTICE。

## 数据源规则

- 生产：`MARKET_PROVIDER=composite`，`ALLOW_MOCK_FALLBACK=false`。
- Mock 只用于测试和页面演示；任何 Mock 结果都必须阻断 actionable。
- 数据源失败必须记录 provider、操作、耗时、记录数和原因。
- 字段单位、复权和时间口径冲突时停止信号，不做猜测。

## 策略修改规则

修改以下任一内容时必须升级版本：

- 指标公式或初始化；
- 预测特征、邻居选择或标签；
- 信号权重和阈值；
- 市场门控；
- 组合上限和迟滞；
- 数据字段口径。

必须运行：

```bash
pytest -q
python -m compileall -q backend/app
node --check backend/app/static/app.js
```

策略封版前还必须产生：

- 时间序列 walk-forward 报告；
- 事件驱动组合回测；
- 与上一版本和基准的比较；
- 数据泄漏检查；
- 人工批准记录。

## 第三方源码

`vendor/src` 不在运行时路径。`scripts/fetch_reference_sources.sh` 只允许浅克隆 manifest 中 `auto_fetch=true` 的仓库。标记为手工审查的仓库不得由 Agent 自动克隆进生产 ECS。

## 生产变更

- 先备份；
- 只做可回滚变更；
- `git pull --ff-only`；
- 通过 CI/测试后部署；
- 查看 API、scheduler 和 provider audit；
- 失败立即回滚，不做“临时静默降级”。


<!-- BEGIN:codex-project-hub:etf-fund-analysis:v1 -->
## Local project hub reporting (owner-authorized)
- Hub project_id: `etf-fund-analysis`. Registered root: `E:\project\ETF-Fund-Analysis`. These are hub identities; do not change the project's own binding, goals, roadmap or gates.
- After a plan changes, a significant stage ends, tests finish, a blocker appears, and before stopping: report a short structured update. Do not report every chat message.
- Use `E:\project\codex-project-hub\integration\bound_report.py` (deterministic wrapper around the existing report.py CLI). Pass `--project etf-fund-analysis --worktree "ACTUAL-WORKTREE-ROOT"`; use the registered root only when actually working there. Branch is read from that worktree; detached HEAD and non-Git UNVERSIONED are explicit. Never reuse another worktree's identity/revision.
- Read the revision first: `python E:\project\codex-project-hub\integration\bound_report.py --project etf-fund-analysis --worktree "ACTUAL-WORKTREE-ROOT" revision`.
- Generate a new event: same prefix plus `template --agent "ACTUAL-AGENT-ID" --run "ACTUAL-RUN-ID" --revision N`; save stdout as UTF-8 to `E:\project\codex-project-hub\reports\etf-fund-analysis-EVENT-ID.json`. Fill current/next/blockers, stage_id and version/test/artifact references using the returned definition; then call the same prefix plus `send "ABSOLUTE-REPORT-FILE"`.
- Only claim tests you actually ran; label inherited/source-document claims and imports with source revision/date and importer role. Never claim another Agent called the CLI. Preserve pending planning (including PENDING_REMOTE_PLANNING); old connection warnings require current confirmation.
- Status reporting cannot change final goals/routes or grant approval. No owner.py apply from ordinary Agent reporting; claimed completion is not verified acceptance. No HTML edits, credentials, private photos, account data, raw sensitive logs or chat transcripts in reports.
- On failure keep the pending JSON, clearly report the error and path, and stop automatic retries. Retry an unchanged event_id/content after connectivity recovers; on 409 inspect latest revision and manually reconcile into a new event. Never silently overwrite or claim success without a successful CLI result.
- Full contract/commands: `E:\project\codex-project-hub\reports\etf-fund-analysis-INTEGRATION.md`. Reporting does not expand the project's execution permissions or start/continue another Agent session.
- This block applies after the Agent actually reads this file; old sessions are not assumed to reload it. Independent worktree copies must be checked separately.
<!-- END:codex-project-hub:etf-fund-analysis:v1 -->
