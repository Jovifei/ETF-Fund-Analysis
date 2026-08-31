# ETF 14:30 验证清单

## 代码门禁

```bash
pytest -q
python -m compileall -q backend/app
node --check backend/app/static/app.js
node --check backend/app/static/etf_1430_workbench.js
python codex/skills/fund-research/scripts/check_no_secrets.py .
bash -n scripts/run_1430_decision.sh
```

## 浏览器门禁

在 1440、1024 和 390 像素宽度检查：

- 排名表；
- 1/3/5/10 日预测；
- 历史与预测情景分界；
- 支撑和压力线；
- 综合、均线、MACD、KDJ、RSI、缠论近似、成交密集模式；
- `not_calibrated` 和研究边界；
- 原主看板无回归。

## 真实数据门禁

- Tushare/AKShare 能力矩阵；
- 上游 source timestamp；
- 5/15 分钟数据；
- 截至 14:30 的量能和 VWAP；
- 14:30 后第一条可成交价格；
- 新闻 point-in-time；
- 最近 6–12 个月隔离 Holdout。

## 预测指标

- direction accuracy；
- Brier Score；
- MAE；
- pinball loss；
- 80%/90% coverage；
- interval width；
- quantile crossing；
- path-low/path-high coverage；
- support/resistance touch Brier。

## 结论边界

远端/Mock 测试通过不等于真实 14:30 策略通过。真实分钟数据、费用、滑点和影子运行完成前，必须保持 `historical_1430_backtest=not_qualified`。
