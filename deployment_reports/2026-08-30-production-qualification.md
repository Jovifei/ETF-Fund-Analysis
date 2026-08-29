# v0.7.0 生产资格验证报告（本地阶段）

生成时间：2026-08-30（Asia/Shanghai）  
状态：**本地/Mock 阶段完成；真实数据与 ECS 阶段阻塞**

---

## 1. 版本与 commit

| 项 | 值 |
|---|---|
| Git commit | `121f70fe91a10f83bf5a885b097f03b268ceed88`（本轮修复另含未提交变更） |
| 应用版本 | `0.7.0` |
| 策略 | `signal-v0.7.0-research` |
| 指标 | `indicator-v0.5.1` |
| 预测 | `similarity-corridor-v0.7.0` |
| 回测 | `rotation-v0.5.1` |
| 特征 Schema | `feature-store-v0.7.0` |
| Alembic head | `d5e6f7a8b9c0` |

## 2. 运行环境

| 组件 | 版本 |
|---|---|
| OS | Windows 10 (22631) |
| Python | 3.12.10 |
| Docker | 29.7.2 |
| Docker Compose | v5.4.0 |
| PostgreSQL（隔离演练） | `postgres:16-alpine` |

## 3. 测试结果

- `pytest -q`：退出码 0（352 passed + 2 skipped，与 Phase A 基线一致）
- compileall / node / secret scan：通过
- Mock 研究任务：validate_forecasts、calibrate_forecasts、backtest_rotation/ablation/crosscheck、optimize_portfolio、analyze_factors、research_capabilities、shadow_run_audit 均 exit 0（SQLite + Mock provider）

## 4. 迁移与恢复

| 步骤 | 状态 |
|---|---|
| 隔离 PG16 容器启动 | 通过 |
| `alembic upgrade head` → `d5e6f7a8b9c0` | 通过 |
| `alembic downgrade c4d5e6f7a8b9` | 通过 |
| `alembic upgrade head`（再次） | 通过 |
| pg_dump + SHA-256 + wipe + restore + 完整性核对 | **未执行**（需 Linux 上完整 `qualify_postgres.sh`） |

详见 `deployment_reports/pg-qualification.json`。

## 5. Provider 能力矩阵

| Provider | 状态 |
|---|---|
| Tushare | **未验证** — `TUSHARE_TOKEN: missing` |
| AKShare | **未验证** — 无真实网络资格跑分 |
| Composite | **未验证** |
| Mock 结构检查 | `--allow-mock-check` exit 0；全部 `actionable=false`（符合预期） |

`scripts/qualify_market_data.py` 默认拒绝 Mock（exit 3）。真实矩阵输出路径：`deployment_reports/provider-qualification.json`（待 Token 配置后生成）。

## 6. ETF/LOF 池与历史数据

| 项 | 状态 |
|---|---|
| `build_etf_universe.py` dry-run | exit 3 `token_missing` |
| watchlist 写入 | 未执行（需人工审阅 + `--confirm-private-use`） |
| 五年日线导入 | 未执行（依赖 Tushare） |
| 10 只 × 60 日双源核对 | 未执行 |

Mock 本地：`refresh_bars --lookback-days 2200` 在本轮修复回填逻辑后插入 12726 条 bar（9 instruments）。

## 7. 实时行情资格

未获得真实盘中数据。Mock quotes 全部 `degraded`，`actionable=false`。

## 8. 预测验证

- `validate_forecasts`：Mock 9 instruments；输出 `reports/forecast_validation_*.json`
- `calibrate_forecasts`：候选 Profile 已生成；**未人工批准**；预测状态保持 `not_calibrated`

## 9. 因子验证

- `analyze_factors`：30 factors，9 instruments（Mock）；报告 `reports/factor_effectiveness_*.json`
- 真实横截面与 Holdout：**未完成**

## 10. 回测与第二引擎

- `backtest_rotation` / `backtest_ablation`：Mock exit 0
- `backtest_crosscheck`：Mock 对账 exit 0
- 真实费率/涨跌停/LOF 溢价约束：**未在真实数据验证**

## 11. 组合研究

- `optimize_portfolio`：等权/得分倾斜/风险预算三策略 JSON；**不写 Holding**

## 12. 新闻与 LLM

- `refresh_news` / `analyze_news`：本轮未单独重跑；`OPENAI_API_KEY: missing`

## 13. 集成资格

- `research_capabilities`：exit 0；Qlib/FinGPT/vectorbt/RD-Agent 等保持 `research_only` / `unavailable`（见 `config/integration_registry.json`）

## 14. 影子运行

- `shadow_run_audit`：Mock 单次烟测通过
- **≥20 真实交易日连续影子运行：未开始**（需 ECS + scheduler 前先完成 D/E/F）

## 15. 阿里云 ECS

| 项 | 状态 |
|---|---|
| `bootstrap_host.sh` | 未在本机执行（需 ECS） |
| Docker 镜像构建 / Compose up | 阻塞：无 `.env` |
| Scheduler | 保持 `SCHEDULER_ENABLED=false`（推荐） |

## 16. 未完成项（按优先级）

1. 用户配置 `TUSHARE_TOKEN`（及可选 LLM 密钥）到私有 `.env`
2. Linux ECS 上完整 `qualify_postgres.sh` 九步 + Provider 真实矩阵
3. ETF 池 dry-run → 人工审阅 → `--write-watchlist --confirm-private-use`
4. 真实五年数据导入与 10 只双源核对
5. walk-forward / Holdout 预测校准与人工批准
6. 20 交易日影子运行后启用 scheduler

## 17. 回滚点

- Git：`121f70fe91a10f83bf5a885b097f03b268ceed88`（Phase A 完成点）
- 数据库：生产未部署；本地 SQLite 可随时删除重建
- 策略配置：未修改 `config/strategy.json` 阈值

---

本报告不含 Token、密码、公网 IP 或持仓截图。
