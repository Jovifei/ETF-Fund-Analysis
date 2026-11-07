# Validation Report

验证日期：2026-08-29（Asia/Shanghai）  
工程版本：0.7.0

## 本版本自动门禁

本提交只有在隔离 GitHub Actions 工作流完成以下步骤后才允许快进到 `main`：

- 完整 `pytest -q`；
- Python compileall；
- 浏览器 JavaScript 语法；
- committed-secret scan；
- Alembic 干净数据库 `upgrade head` 与 `downgrade`/再次升级；
- ShellCheck；
- Docker Compose 配置；
- 生产 Docker 镜像构建；
- Mock bootstrap、预测验证、轮动回测、策略消融和因子分析烟测。

## v0.7.0 新增验证对象

- 1/5/20 日终点收益与价格区间；
- 未来路径最低/最高价格分位区间；
- 支撑/压力触及概率；
- pinball loss、80%/90% coverage、interval width、quantile crossing；
- 因子 IC、Rank IC、ICIR、分位收益、换手率、主题和市场状态分组；
- 指标/预测快照的 Git、配置和特征 Schema 复现信息；
- XSHG 交易日历与行情源时间戳 fail-closed 门控。

## 仍未获得的证据

真实 Tushare/AKShare 权限与 ECS 出口、真实 PostgreSQL 备份恢复、真实 50–150 只 ETF 池、真实 walk-forward/holdout、LightGBM/CatBoost/MLForecast/MAPIE/AKQuant/RQAlpha 第二环境，以及 20 个交易日影子运行仍需目标环境完成。预测继续保持 `not_calibrated`。

## Main one-shot publication gate

- pytest: passed
- compileall / browser JS / secret scan: passed
- Alembic upgrade-downgrade-reupgrade: passed
- ShellCheck / Compose / production image: passed
- Mock forecast / corridor / factor / backtest research smoke: passed
- real provider and ECS qualification: not executed by CI

## ETF 14:30 Workbench 覆盖包

新增模块必须执行：完整 pytest、compileall、主 JS 与 `etf_1430_workbench.js` 语法、密钥扫描、Bash/ShellCheck、Mock API 和浏览器尺寸验收。远端环境无法替代真实 5/15 分钟 point-in-time、Provider、PostgreSQL、CZSC 和 ECS timer 验证。
