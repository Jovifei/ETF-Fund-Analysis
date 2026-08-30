# 截图同款 ETF 信号分级页面

本页是 `feat/screenshot-signal-board-v2` 的功能规格。目标是复刻任务截图的**信息结构、颜色语义和交互能力**，而不是复制来源页面的商标、账户数据或不可验证结论。

## 页面结构

1. 彩色汇总卡：行业覆盖、可加仓、可入场、可试探、观望、减仓/异常。
2. 红色盘中总结：上涨/下跌代理数、领先标的、风险标的、预测边界。
3. 四张市场锚卡：沪深300、标普500ETF代理、纳指ETF代理、黄金ETF。
4. 申万2021版31个一级行业标签。
5. 五级信号表：可加仓、可入场、可试探、观望、减仓。
6. 列：标的、今日涨幅、较上一信号、量能、均线、MACD、KDJ、TD、RSI、板块ETF代理宽度、近1周、明日预测、建议。
7. 底部两张证据卡：盘中核心变化、明日预测与置信度解读。

## 颜色约定

中国市场采用红涨绿跌。绿色/蓝色也用于“结构正向”徽标，因此数值涨跌必须同时保留正负号，避免只靠颜色表达。橙色表示偏高或需要观察，红色风险徽标表示死叉、超买、TD顶部序列或减仓状态，紫色表示MACD转弱。

## 信号分组

- `可加仓`：已有风险暴露或高分趋势延续，且KDJ不过热。
- `可入场`：结构和趋势较好，适合作为新候选。
- `可试探`：证据尚未完全一致，只适合研究性小仓验证。
- `观望`：超买、偏高、放量滞涨或证据冲突。
- `减仓`：KDJ/MACD转弱、TD顶部风险、得分显著下降或数据异常。

分组只对当前持久化信号做展示映射，不在浏览器中重算生产信号权重。

## 真实性边界

- `板块涨跌` 是同一宏观组内**ETF代理池**的上涨/下跌数量，不是行业全部成份股家数。
- `513500.SH` 和 `513100.SH` 是中国场内QDII ETF代理，不等同于美国指数实时点位。
- ETF/LOF筹码字段使用 `volume_profile_approx`，不能称为真实股东筹码。
- 未完成真实基金池 walk-forward 校准前，预测必须显示 `not_calibrated`。
- 行情源时间未通过资格验证时，`actionable=false`。

## 相关文件

- `config/industry_board.json`
- `backend/app/services/industry_board_service.py`
- `backend/app/services/screenshot_signal_board_service.py`
- `backend/app/static/screenshot_signal_board.html`
- `backend/app/static/screenshot_signal_board.css`
- `backend/app/static/screenshot_signal_board.js`
