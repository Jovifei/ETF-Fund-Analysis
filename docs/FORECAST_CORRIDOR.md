# 预测走廊（Forecast Corridor）当前合同

更新时间：2026-09-06

## 1. 当前 horizon

当前新生成的 forecast / factor / 14:30 研究期限统一为：

```text
1 / 3 / 5 / 10 trading sessions
```

这是 `HORIZON_ALIGNMENT_20260903.md` 锁定的当前代码合同。

历史 v0.7 文档和已持久化旧 artifact 曾使用 `1/5/20`。20 日 feature lookup 可以为历史 artifact 复现保留，但 **20D 不属于当前新运行配置**；若以后重新启用，必须单独建立 h=20 的 purged walk-forward、校准和人工批准。

---

## 2. 走廊输出是什么

对当前每个 horizon（1/3/5/10），ForecastSnapshot 可包含：

### 终点分布

- `q10 / q50 / q90`：终点收益分位数；
- `terminal_price_q10 / q50 / q90`：终点价格情景分位数。

### 路径低点/高点

- `path_low_price_q10 / q50 / q90`：预测路径期间最低价的研究分位数；
- `path_high_price_q10 / q50 / q90`：预测路径期间最高价的研究分位数。

### 支撑/压力触及

- `support_touch_probability`；
- `resistance_touch_probability`。

### 走廊位置

`corridor_position`（0–100）表示当前价格在路径低点/高点中位情景之间的位置，用于研究解释，不是交易阈值本身。

---

## 3. 数据与算法边界

当前 forecast 的权威是**持久化 ForecastSnapshot**，页面不得在浏览器或每次 HTTP 请求中临时再训练/重算一个不同模型。

相似样本/全局研究服务可以产生候选研究结果，但写入/读取时必须保留：

- horizon；
- feature schema/version；
- model/version；
- as_of_date；
- data_cutoff；
- generated_at；
- sample_count；
- confidence；
- calibration_status；
- interval_method。

14:30 的 provisional 当日状态可以用于当前指标、grade、S/R 和图表，但不能偷偷进入以已结算日线为邻居的 EOD forecast baseline。

---

## 4. `p_up` 文案合同

### 未校准

当：

```text
calibration_status != calibrated
```

`p_up` 只能解释为：

> 历史相似样本上涨占比

不能写“未来上涨概率”。

### 已校准

只有某个 horizon 经过样本外校准门禁并人工批准，且 snapshot 明确写入：

```text
calibration_status = calibrated
```

页面才允许使用“上涨概率”文案。

---

## 5. Forecast scenario 蜡烛/走廊

未来可视化只是条件化研究情景：

```text
is_forecast = true
not_actual = true
```

必须与历史真实 K 线有明确视觉分界（当前 UI 使用独立紫色/虚线/半透明语义）。

它不能被描述为未来真实 OHLC，也不能用于回填任何历史 point-in-time 特征。

---

## 6. 研究级 interval 加宽

历史实现包含 `local_conformal_research_v1` 等研究级残差加宽方法。例如概念上可使用：

```text
correction = quantile(|actual - q50|, clamp(1 - alpha, 0.5, 0.99))
conformal_q10 = min(q10, expected - correction)
conformal_q90 = max(q90, expected + correction)
```

这类研究加宽**本身不等于完成正式校准**。是否 calibrated 只由对应 horizon 的 OOS 验证和人工批准决定。

---

## 7. 最终必须验证的指标

每个 1/3/5/10 horizon 分开报告：

| 指标 | 目的 |
|---|---|
| direction accuracy | 方向识别 |
| Brier Score | 概率/上涨占比校准质量（在适用语义下） |
| MAE | 中心预测误差 |
| pinball loss | q10/q50/q90 分位数质量 |
| interval_80_coverage | 80% 区间覆盖 |
| interval_90_coverage | 90% 区间覆盖 |
| interval mean width | 区间是否过宽 |
| quantile_crossing_rate | 分位数合法性 |
| path_low coverage | 路径低点区间质量 |
| path_high coverage | 路径高点区间质量 |
| support_touch_brier | 支撑触及研究质量 |
| resistance_touch_brier | 压力触及研究质量 |

验证必须使用 purged/rolling walk-forward 和真正隔离的 Holdout，不能根据 Holdout 反复调参后继续称其为样本外结果。

---

## 8. 对 current action 的边界

Forecast Corridor 不拥有 current action。

- canonical current action 由当前决策合同统一提供；
- 未 calibrated forecast 不应直接驱动生产动作阈值；
- `research_score` 可以引用 forecast 作为排序/解释证据，但不能创造第二套“买/卖”结论；
- Mock/stale/unverified forecast 继续受数据资格门控。

详细验证路径见 `ETF_1430_VALIDATION.md` 和 `ROADMAP_TO_FINAL.md`。
