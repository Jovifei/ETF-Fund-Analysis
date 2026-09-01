# WorkBuddy 风格 ETF 决策评分台

## 目标

本分支新增一套独立的决策看板视觉实验，重点复刻用户要求的“评分清晰、颜色清晰、指标解释清晰、来源清晰”体验，同时保留现有工程独有能力：

- 五档研究分级：可加仓 / 可入场 / 可试探 / 观望 / 减仓；
- 点击 ETF 查看历史 K 线和未来研究情景 K 线；
- 1 / 3 / 5 / 10 日预测；
- 支撑、压力和 `chan_zone_approx`；
- Provider 来源、源时间和资格状态；
- Mock / stale / unverified 明确降权，不冒充真实。

> WorkBuddy 分享链接当前无法从自动抓取环境读取动态页面，因此本分支不宣称像素级复制外站；实现依据用户明确描述、此前任务截图和本项目已有数据契约，复刻其核心信息架构：每只 ETF 有综合得分、颜色、指标解释、J=90 阈值、预测周期、来源/时效和分组。

## 页面

本实验分支将 `/` 切到新的评分看板，完整多页签系统保留在 `/legacy`。

静态资源：

- `backend/app/static/decision_board_workbuddy.html`
- `backend/app/static/decision_board_workbuddy.css`
- `backend/app/static/decision_board_workbuddy.js`
- `backend/app/static/decision_board_workbuddy.test.js`

## 综合评分

评分为**读取层研究评分**，不修改 `SignalV05Service`、`signal_grade` 或任何生产阈值：

| 维度 | 权重 |
|---|---:|
| 趋势（MA + MACD） | 22% |
| 动量（KDJ + RSI + TD9） | 22% |
| 量能 | 14% |
| 结构/支撑压力 | 14% |
| 当前所选期限预测 | 20% |
| 数据资格 | 8% |

分数颜色遵循中国行情页“红强绿弱”的视觉习惯：

- 85–100：强共振（红）
- 70–84：偏强（橙）
- 55–69：结构尚可（金）
- 40–54：谨慎（蓝）
- 0–39：风险偏高（绿）

分数不是收益概率，也不覆盖生产分级；生产分级继续由后端五档规则给出。

## KDJ J 值解释

页面明确采用：

- `J > 100`：超买/钝化，短线回撤风险高；
- `90 <= J <= 100`：偏热，不追高；
- `70 <= J < 90`：偏强但仍有余量；
- `30 <= J < 70`：健康区；
- `10 <= J < 30`：低位，等待拐头；
- `J < 10`：极低/超卖，但不等于立即买入；
- KDJ 死叉优先降分。

## 我们相对参考页的优势

1. **同一 ETF 点击后可看到历史蜡烛 + 未来研究情景蜡烛**，且预测区域明确标记非实际结果。
2. **1/3/5/10 日预测在同一详情页并列显示**，未校准时继续显示 `not_calibrated`。
3. **支撑/压力和缠论重叠区近似**可以直接叠加到价格图上，而不是只给单一总分。
4. **五档生产读取分级与视觉总分分离**：评分只是解释层，不会偷偷改生产信号。
5. **数据来源和时效资格是显式维度**：Mock、stale、unverified 会直接降低“数据资格”得分并显示警告。
6. **保留完整系统入口 `/legacy`**，持仓、新闻、多模型分析、系统设置等仍可使用。

## 验证

至少执行：

```bash
node --check backend/app/static/decision_board_workbuddy.js
node --test backend/app/static/decision_board_workbuddy.test.js
pytest -q
python -m compileall -q backend/app
```

参考评分只属于 UI/读取层。若未来要把该评分进入策略引擎，必须先进行真实数据 IC、消融、walk-forward 和 Holdout 验证。
