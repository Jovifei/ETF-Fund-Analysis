# Validation Report

验证日期：2026-08-27（Asia/Shanghai）  
工程版本：0.4.0

## 已执行并通过

| 检查 | 结果 |
|---|---|
| `pytest -q` | **8 passed** |
| `python -m compileall -q backend/app` | 通过 |
| `node --check backend/app/static/app.js` | 通过 |
| 提交前密钥扫描 | 未发现明显已提交密钥 |
| 所有 Shell 脚本 `bash -n` | 通过 |
| `docker-compose.yml` YAML/结构检查 | 通过；API 绑定 `127.0.0.1`，数据库无宿主机端口 |
| Alembic 干净数据库升级 | 通过，生成 14 张业务/迁移表 |
| FastAPI TestClient | health、bootstrap、K 线、静态资源、设置、报告列表与下载通过 |
| Mock 完整流水线 | 通过 |
| 相似预测 walk-forward 验证 | 通过并生成 JSON |
| 事件驱动轮动回测 | 通过并生成 JSON；验证收盘决策、次日开盘执行及无前视字段 |

## 干净 Mock 流水线结果

临时数据库和报告目录均位于 `/tmp`，未打包进源码。

- 标的：10 个，其中 9 个启用；
- 日线：2709 条；
- 指标快照：9 条；
- 预测快照：27 条（1/5/20 日）；
- 行情快照：9 条；
- Mock 原始实时标记：9，执行级实时：0，退化：9；
- 新闻：3 条；
- 信号：9 条，`观察` 7、`可试探` 2；
- 市场状态：`normal`，组合暴露上限 70%；
- 报告产物：HTML 看板、预测验证 JSON、轮动回测 JSON。

Mock 数据不会生成可执行信号；示例文件位于 `examples/`。

## Mock 事件驱动回测结果

以下只用于证明引擎能运行，**不是市场表现声明**：

- 决策次数：36；
- 交易次数：134；
- 总收益：-9.6336%；
- 基准收益：-22.1640%；
- 最大回撤：-10.7584%；
- Sharpe：-2.3948；
- 平均暴露：49.85%；
- 报告明确包含 `contains_mock=true`、`decision_at=close_t`、`execution_at=open_t_plus_1`。

## 当前环境无法完成的验证

1. 当前执行环境没有 Docker daemon，因此未实际构建镜像、启动 Compose 或运行 PostgreSQL 容器。
2. 未使用用户的 Tushare Token，无法验证账户积分、实时 ETF、新闻和分钟线权限。
3. 未从目标阿里云 ECS 验证 AKShare 底层站点、RSSHub 或 OpenAI-compatible 端点的出口稳定性。
4. 未配置真实域名、HTTPS、安全组、OSS 异地备份和阿里云云监控。
5. 预测仍为 `not_calibrated`；回测仍需真实停牌/涨跌停/LOF 溢价和独立第二引擎复核。
6. 未实现自动交易，且部署规则禁止 Codex擅自增加自动下单。

服务器部署时必须按照 `CODEX_DEPLOYMENT_TASKS.md` 继续验证，不能把本地 Mock 通过等同于生产数据通过。
