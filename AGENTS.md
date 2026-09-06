# Codex / Agent 操作契约

<!-- BEGIN:codex-token-efficiency -->
## Token-efficient navigation

- Obey the mandatory reading order below, but do not preload any additional history or repository-wide content.
- When `.codegraph/` exists, start code exploration with lightweight CodeGraph tools: file map, symbol search, callers/callees, impact, and single-node lookup. Use broad context/explore only if these are insufficient.
- Use `rg` for exact identifiers, errors, config keys, and headings; read only matching ranges. Read a whole file only when its full behavior is necessary.
- Search documentation names/headings first and open only task-relevant sections. Do not read archived reports, generated output, dependencies, media, databases, or logs by default.
- Run focused checks first. Keep verbose output on disk and return only exit status, failing cases, and the relevant error region.
<!-- END:codex-token-efficiency -->

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
