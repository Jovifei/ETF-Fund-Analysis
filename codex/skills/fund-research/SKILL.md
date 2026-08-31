---
name: fund-research
slug: fund-research
description: 部署、验证和维护中国 ETF/LOF 私有研究看板。用于数据源冒烟、指标核验、预测 walk-forward、组合回测、报告审计和阿里云部署。不得自动下单。
version: 0.4.0
requirements:
  python: 3.11+
  network_access: true
---

# Fund Research Skill

## 使用范围

- 验证 Tushare / AKShare / RSS 数据源；
- 检查 ETF/LOF OHLCV 和实时行情口径；
- 运行确定性指标、预测、信号和报告；
- 运行时间序列预测验证；
- 为后续事件驱动组合回测补充代码和测试；
- 部署或更新阿里云 ECS。
- 运行 ETF 14:30 决策工作台和支撑压力资格检查；

## 禁止事项

- 不显示或提交 API Key、Token、Cookie、密码。
- 不把日线收盘伪装成实时价格。
- 不在核心数据缺失时给操作级结论。
- 不让 LLM 计算指标或修改确定性信号。
- 不自动下单，不添加券商凭据。
- 不把 `not_calibrated` 改成 `calibrated`，除非全部验证门槛通过并有人工作出批准。
- 不自动克隆 `vendor/manifest.json` 中 `auto_fetch=false` 的仓库。

## 标准工作流

1. 读 `AGENTS.md`、`STATUS.md`、`CODEX_DEPLOYMENT_TASKS.md`。
2. 执行本地测试。
3. 启动 db/api，不启动 scheduler。
4. 执行 `scripts/provider_smoke.py`。
5. 按 `references/data-quality-checklist.md` 抽检数据。
6. 运行 bootstrap 和 validate_forecasts。
7. 生成报告，检查证据和过期时间。
8. 人工确认后启动 scheduler。
9. 记录不含密钥的部署报告。

## 常用命令

```bash
pytest -q
python -m compileall -q backend/app
node --check backend/app/static/app.js

docker compose up -d db api
docker compose run --rm api python scripts/provider_smoke.py
docker compose run --rm api fund-decision bootstrap --lookback-days 900
docker compose run --rm api fund-decision run-task validate_forecasts
docker compose up -d scheduler
```

## 修改策略时

先定义假设和失败标准，然后：

- 创建新版本号；
- 保留旧参数；
- 时间切分；
- 输出与基准比较；
- 做事件驱动审计；
- 检查前视、幸存者偏差和数据修订；
- 未通过则保留负结论，不通过调参隐藏。

## ETF 14:30 工作台

涉及 14:30 决策、未来情景蜡烛、支撑压力或缠论近似时，必须先阅读 `references/etf-1430-workbench.md`。

```bash
node --check backend/app/static/etf_1430_workbench.js
python scripts/build_1430_point_in_time_dataset.py --help
```
