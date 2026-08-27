# Validation Report

验证日期：2026-08-27（Asia/Shanghai）  
工程版本：0.5.0

## 已执行并通过

| 检查 | 结果 |
|---|---|
| `pytest -q` | **14 passed** |
| `python -m compileall -q backend/app` | 通过 |
| `node --check backend/app/static/app.js` | 通过 |
| 所有 `scripts/`、`deploy/` Shell 脚本 `bash -n` | 通过 |
| `check_no_secrets.py .` | 未发现明显已提交密钥 |
| Mock `bootstrap --lookback-days 420` | 通过 |
| Mock `backtest_rotation` | 通过 |
| Mock `backtest_ablation` | 通过；4 个变体使用同一事件驱动执行引擎 |
| RSRS 公式专项 | 线性 high~low 样本得到预期 beta=2、R²=1 |
| OBV 已知序列专项 | 通过 |
| MFI/CMF 持续资金流专项 | 通过 |
| v0.5 多策略家族 | 趋势/突破/RPS/资金流共振与风险收缩测试通过 |
| RPS 横截面 + 策略证据落库 | 集成测试通过 |

本地环境没有预装 `ruff` CLI，因此本轮没有伪称本地 `ruff check` 已通过；GitHub CI 仍保留开发依赖，可在 CI/ECS 安装后执行。

## v0.5 指标/策略验证范围

确定性代码现覆盖：

- MA/MACD/KDJ/RSI/ATR/BOLL/TD；
- OBV、MFI(14)、CMF(20)、VWAP20、量比/额比/量能 Z-score；
- ADX/+DI/-DI(14)、CCI(20)、Williams %R(14/28)、ROC(12)；
- 20/55/120 日箱体位置与振幅；
- 海龟 20/55 日突破与 10/20 日退出通道；
- RPS20/60/120 横截面百分位；
- RSRS(18,60)：high~low OLS → beta×R² → rolling z-score；
- 放量点火、缩量回踩、二次启动、支撑失守；
- ETF/LOF 120 日成交密集/成本分布近似：峰值价、近似获利盘、COST15/50/85 与集中度；
- 8 个策略家族：trend、momentum、volume_flow、breakout、pullback、structure、relative_strength、reversal。

ETF/LOF 的“筹码”字段在代码和证据中明确标记为 `volume_profile_approx`，不是股票真实股东筹码分布。

## Mock 事件驱动回测

以下只验证引擎和审计口径，**不是市场业绩声明**。本轮手工 Mock 回归的 `full_v050`：

- 总收益：-11.8134%；
- 基准收益：-22.1640%；
- 最大回撤：-13.0760%；
- Sharpe：-2.9212；
- 交易次数：138；
- 平均暴露：50.38%；
- `decision_at=close_t`；
- `execution_at=open_t_plus_1`；
- `future_data_in_features=false`。

## v0.5 策略消融结果（Mock）

同一数据、同一手续费/滑点、同一次日开盘执行、同一迟滞/仓位/风险门控，只改变因子权重：

| 变体 | 总收益 | Sharpe | 最大回撤 | 相对动量基线总收益变化 |
|---|---:|---:|---:|---:|
| `momentum_baseline` | -9.4776% | -2.3678 | -10.7737% | 0 |
| `plus_volume_flow` | -12.5830% | -3.0594 | -13.8335% | -3.1054pp |
| `plus_breakout_structure` | -13.8945% | -3.4651 | -15.1262% | -4.4169pp |
| `full_v050` | -11.8134% | -2.9212 | -13.0760% | -2.3358pp |

这一结果很重要：**在 Mock 序列上，新因子并没有优于动量基线**。因此 v0.5 的新增因子仍是 `unsealed research baseline`，不能因为指标数量增加就自动提升生产权重。必须用真实 ETF/LOF 历史数据重新做 walk-forward、分市场状态和第二引擎复核。

## 当前环境无法完成的验证

1. 未使用用户 Tushare Token，无法验证账户积分、实时 ETF、新闻、分钟线和基金扩展字段权限。
2. 当前执行环境没有 Docker daemon，未实际构建/启动 Compose/PostgreSQL 容器。
3. 未从目标阿里云 ECS 验证 AKShare 底层站点、RSSHub 或 OpenAI-compatible 端点的出口稳定性。
4. 未配置真实域名、HTTPS、安全组、OSS/异地备份和阿里云云监控。
5. 预测仍为 `not_calibrated`。
6. 真实回测仍需停牌/涨跌停、LOF 溢价/申赎、现金收益和独立第二引擎对账。
7. 自动交易未实现，且 Agent 契约禁止部署时擅自增加。

服务器部署必须继续按 `CODEX_DEPLOYMENT_TASKS.md` 验证；本地 Mock 通过不能替代真实市场验证。
