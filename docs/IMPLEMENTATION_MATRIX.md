# 实现矩阵

| 需求 | 实现位置 | 当前状态 | 部署后任务 |
|---|---|---|---|
| 暗色决策看板 | `backend/app/static` | 完成 | 真实数据视觉验收 |
| 行情 3 分钟 | scheduler + RuntimeSetting | 完成 | 观察 Tushare 限频和耗时 |
| 信号 10～15 分钟可调 | 网页设置 + scheduler | 完成 | 选定最终默认值 |
| 午间高频新闻 | MarketClock + scheduler | 完成 | 配新闻权限/RSS |
| MACD/KDJ/蜡烛图 | indicators + Canvas | 完成 | 与可靠终端抽检口径 |
| ETF/LOF | watchlist + Providers | 完成基础 | 扩充真实池和元数据 |
| 持仓录入 | Holding API/UI | 完成 | 录入用户持仓 |
| 今日操作状态 | SignalService | 完成基线 | 真实数据回测与人工封版 |
| 明日/一周/一月预测 | ForecastService | 完成基线 | 真实 walk-forward 校准 |
| 新闻热点 | Tushare + optional RSS | 完成 | 验证新闻权限和源 |
| OpenAI-compatible 解读 | LLM service | 完成 | 实测模型 JSON Schema |
| 数据源降级 | CompositeProvider | 完成 | 阿里云出口冒烟 |
| 证据链 | hashes/audits/snapshots | 完成 | 检查报告完整性 |
| HTML/JSON 报告 | ReportService / Validation / Backtest | 完成 | 域名下载体验与长期归档 |
| 事件驱动轮动回测 | `RotationBacktestService` | 完成研究基线 | 补停牌/涨跌停/LOF 溢价和第二引擎对账 |
| 定时任务 | Python scheduler | 完成 | 完整交易日观察 |
| 并发保护 | PostgreSQL advisory lock | 完成 | PostgreSQL 实测 |
| 阿里云部署 | Compose + scripts | 已实现 | 在目标 ECS 执行 |
| HTTPS | Caddy/Nginx example | 模板 | 域名和证书配置 |
| 备份 | pg_dump/restore scripts | 完成脚本 | 异地备份和恢复演练 |
| 自动交易 | 无 | 明确不做 | 不应由 Codex擅自增加 |
