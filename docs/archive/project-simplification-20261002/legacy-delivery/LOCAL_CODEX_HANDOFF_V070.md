# 本地 Codex 交接：v0.7.0

本地 Agent 拉取后先阅读 `AGENTS.md`、`STATUS.md`、`VALIDATION.md` 和 `docs/ROADMAP_V070.md`。不要读取或输出 `.env`。

## 已由仓库完成

- 发布门禁、版本与密钥扫描修复；
- XSHG 交易日历；
- 上游行情时间戳资格门控；
- 统一高级 Feature Store；
- 1/5/20 日终点与路径低高价格走廊；
- 支撑/压力触及概率；
- 预测区间验证指标；
- 因子有效性任务；
- 可选 LightGBM/CatBoost 全局模型研究任务；
- 快照复现元数据与数据库迁移；
- 页面价格走廊展示。

## 只能在本地/ECS完成

- 写入真实 Token 和数据库密码；
- Tushare/AKShare 权限、实时源时间戳和出口稳定性；
- 真实 PostgreSQL 迁移、备份恢复；
- 50–150 只真实 ETF/LOF 池和至少五年日线；
- 安装 `.[research]` 后运行 MAPIE/MLForecast/LightGBM/CatBoost/AKQuant/RQAlpha 对账；
- 真实 walk-forward、完全隔离 Holdout 和 20 日影子运行；
- 人工决定是否晋升任何模型。
