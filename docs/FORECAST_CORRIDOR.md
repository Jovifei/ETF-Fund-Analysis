# 预测走廊（Forecast Corridor）

## 概述

v0.7.0 引入的预测走廊系统，在 1/5/20 日终点预测的基础上，增加了路径低点/高点价格走廊、支撑/压力触及概率和走廊位置指标。所有输出均为研究级（research-grade），状态始终为 `not_calibrated`。

## 路径低点/高点价格走廊

对每个 horizon（1/5/20 日）：

- **path_low_price_q10/q50/q90**：预测路径期间最低价的分位数
- **path_high_price_q10/q50/q90**：预测路径期间最高价的分位数

计算方法：使用相似样本法（similarity-based），特征向量加权邻居的未来路径最低/最高价格分位数。

## 支撑/压力触及概率

- **support_touch_probability**：预测路径最低价触及支撑位的概率
- **resistance_touch_probability**：预测路径最高价触及压力位的概率

支撑位：BOLL 下轨 → MA20；压力位：BOLL 上轨（取可用值）。

## 走廊位置

`corridor_position`（0-100）：当前收盘价在 path_low_q50 与 path_high_q50 之间的相对位置。

## 校准状态

`calibration_status` 始终为 `not_calibrated`。走廊宽度使用 `local_conformal_research_v1` 方法进行研究级加宽：

```
correction = quantile(|actual - q50|, clamp(1 - alpha, 0.5, 0.99))
conformal_q10 = min(q10, expected - correction)
conformal_q90 = max(q90, expected + correction)
```

这是研究级残差加宽，**不是正式的 MAPIE 校准**，状态保持 `not_calibrated`。

## 验证指标

`validate_forecasts` 输出以下走廊相关指标：

| 指标 | 说明 |
|---|---|
| interval_80_coverage | q10-q90 区间覆盖率 |
| interval_90_coverage | q05-q95 区间覆盖率 |
| interval_80_mean_width | 80% 区间平均宽度 |
| interval_90_mean_width | 90% 区间平均宽度 |
| quantile_crossing_rate | q10>q50 或 q50>q90 的比例 |
| path_low coverage | 路径低点 80% 区间覆盖率 |
| path_high coverage | 路径高点 80% 区间覆盖率 |
| support_touch_brier | 支撑触及概率的 Brier Score |
| resistance_touch_brier | 压力触及概率的 Brier Score |
| pinball_loss | q10/q50/q90 的 Pinball Loss |

## 从 v0.6.0 迁移

- `forecast_snapshots` 表新增 12 个走廊列 + `interval_method`（迁移 d5e6f7a8b9c0 → c4d5e6f7a8b9）
- 预测特征从 v0.6.0 的 12 个扩展到 `feature-store-v0.7.0`（含 ADX/DMI/OBV/MFI/CMF/RPS/RSRS/箱体/海龟/缩量回踩/volume_profile_approx）

## 生产决策边界

走廊预测**不直接修改信号权重或仓位**。`signal.forecast_risk_adjustment.requires_calibrated: true` 意味着只有当预测被标记为 `calibrated` 时才会参与信号调整——目前为 `not_calibrated`，因此不参与。
