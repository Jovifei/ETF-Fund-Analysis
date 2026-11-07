# v0.7.0 发布记录

发布日期：2026-08-29  
发行 Tag：`v0.7.0`  
核心发行提交：`878e22597956a0712ea208f7352565cee6645a87`

## 已完成

- 1、5、20 个交易日终点收益预测继续保留相似样本基线；
- 新增终点收盘价格分位、未来路径低点/高点区间、预测走廊位置，以及支撑/压力触及概率；
- 高级指标进入统一 Feature Store，包括 ADX/DMI、OBV、MFI、CMF、RPS、RSRS、箱体、海龟、回踩和成交密集成本近似；
- 新增方向准确率、Brier、MAE、pinball loss、80%/90% coverage、区间宽度、quantile crossing、路径覆盖和触及概率 Brier 验证；
- 新增 Alphalens 风格因子 IC、Rank IC、ICIR、分位收益和换手分析；
- 新增可选 LightGBM/CatBoost 全局分位模型研究任务；
- 统一 XSHG 交易日历，并将上游行情源时间与本地抓取时间分开；
- 指标和预测快照增加 Git SHA、配置哈希和 Feature Schema 版本；
- 修复提交密钥扫描误报、测试占位令牌、Pydantic 测试构造和因子分析隐式 SciPy 依赖；
- Alembic 新迁移支持升级、降级和再次升级。

## 发布门禁

发布流水线已通过：

- 完整 pytest；
- Python compileall；
- 浏览器 JavaScript 语法检查；
- committed-secret scan；
- Alembic upgrade / downgrade / upgrade；
- ShellCheck；
- Docker Compose config；
- 生产 Docker 镜像构建；
- Mock bootstrap；
- 预测验证；
- 轮动回测；
- 策略消融；
- 因子分析；
- 研究依赖能力检查和全局模型研究任务。

## 尚未获得的证据

本次发布不代表以下内容已通过：

- 用户 Tushare Token 的真实接口权限；
- 阿里云 ECS 对 Tushare、AKShare、RSS 和模型端点的长期稳定性；
- 50–150 只真实 ETF/LOF 池和五年以上真实历史数据；
- 真实 PostgreSQL 备份恢复演练；
- MAPIE/MLForecast/AKQuant/RQAlpha 等独立实现对账；
- 最近 6–12 个月完全隔离 Holdout；
- 20 个真实交易日影子运行；
- 预测从 `not_calibrated` 晋升。

部署和真实资格验证请按 `docs/LOCAL_AGENT_PROMPT_V070.md` 与 `CODEX_DEPLOYMENT_TASKS.md` 执行。任何源时间未认证、数据过期、Mock 或退化行情必须保持 `actionable=false`。
