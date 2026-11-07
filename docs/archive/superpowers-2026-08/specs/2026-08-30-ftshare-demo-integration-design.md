# FTShare 接入与安全演示模式设计

## 决策

- Codex 用户侧同时配置 FTShare MCP 与固定提交的 `ftshare-market-data` Skill；两者只读，不获得业务数据库、持仓或交易权限。
- 业务应用新增默认关闭的 `FTShareProvider`。应用不执行第三方 Skill 脚本；Provider 通过固定白名单 HTTP 契约读取 FTShare，并统一转换为现有 Provider records。
- FTShare 未通过 ETF 列表、日线、现价、字段单位和时间戳资格前，不进入自动 Provider 链。免费档保持 AKShare 主源，完整档保持 Tushare 主源。
- 演示模式使用进程内隔离 SQLite/StaticPool 和 MockProvider，不写生产 PostgreSQL、持仓、ProviderAudit 或正式报告；所有结果固定 `demo/is_mock/research_only=true`、`actionable=false`。
- “更新日线”从 30 个自然日改为 120 天。空库、历史不足、数据源失败和指标失败使用互斥状态，不再全部显示“数据异常”。

## 数据流

```text
Codex -> FTShare MCP / Skill -> 只读研究回答

FTShare HTTP -> FTShareProvider -> Instrument/Bar/Quote records
             -> MarketService/provider_audit -> 指标/分级

Demo endpoint -> isolated SQLite -> MockProvider -> 420 日 bars
              -> indicators/forecasts/signals/grade/boards -> Demo UI
```

## 安全和失败边界

- FTShare URL、工具、日期范围、分页和输出数量由配置/代码白名单固定；前端不得传入任意 URL、工具名或 Shell 参数。
- 返回数据是不可信输入：校验代码、日期、OHLC、重复、未来时间、单位、分页、截断和 source metadata。
- FTShare `UPSTREAM_REJECTED`、schema mismatch、超时或空数据记录脱敏审计并回退下一公开源；禁止回退 Mock。
- 第三方 Skill 不进入 Docker/API 运行时，不提交到业务仓库；记录仓库、固定 commit、MIT 代码许可证与独立数据服务条款。
- 演示数据库仅在进程内存在，重启即丢弃；正式任务在演示视图中禁用。

## 接口

- 配置：`FTSHARE_ENABLED=false`、base URL、timeout、最大页数/记录数/日期跨度。
- Provider 模式新增 `ftshare`（显式资格测试）和 `public_composite`（AKShare -> 已启用 FTShare）。
- 完整 `composite` 顺序：Tushare -> AKShare -> 已启用 FTShare。
- 私有演示 API：`POST /api/demo/load`、`GET /api/demo/bootstrap`、`POST /api/demo/reset`。
- 市场探测返回逐 Provider operation/status/records/latency/failure_class/qualification，永不回显凭据。

## 验收

- UI 等价 30 日请求稳定复现指标全跳过；120 日请求生成指标和非异常分级。
- Demo 加载前后生产数据库核心表计数完全不变；启用标的均有指标，`数据异常=0`，全部 non-actionable。
- FTShare contract tests 覆盖正常、分页、截断、空数据、非法字段、重复、未来日期、超限、超时与 upstream rejection。
- Agent 配置可列出 MCP，Skill commit/域名固定；live probe 仅为资格证据，不成为单元测试依赖。

