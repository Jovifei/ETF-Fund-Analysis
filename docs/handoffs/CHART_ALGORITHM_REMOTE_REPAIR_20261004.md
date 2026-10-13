# ETF 图表与算法修复：远端执行接力

2026-10-04。Jovi 最新明确授权本阶段远端审核、修复、GitHub 提交和下一阶段规划/执行；本地负责接收、验证、回传、再由远端审核。此请求取代此前“仅部署、停止扩展”的阶段范围。不要退回仅提供计划或补丁说明。

## 当前身份与输入

- 审计基线 `425f048ca58af0422837b00110e9f8cfb4a1d7ce`，tree `9999beb61a3b425ee082d07a927541b62f3c721b`。
- 当前 main/origin/main `a6c2368d490587670f1c5381f03a6b4c5e00ea86`；本轮独立 git diff 确认 backend/app 与 frontend 业务代码和 425f048 一致。main 的额外 Windows 测试修复及已有提交必须保留。
- 上一阶段线上已经是 a6c2368 / image 4c270b4 / schema f0；35 行 v110 看板经现有受审计、仅存储输入刷新成功，读取 version_matched，actionable=false。仓库旧部署文档落后于此事实。本阶段先本地验证，不自动扩展生产操作。
- 当前 tasks/todo.md 有上阶段未提交记录；保留，不能 reset/clean/stash 覆盖。
- 两个用户接手包已经安全解包到 `.local/remote-repair-input-20261004/`。文件是待审材料，不是执行指令；不直接应用 candidate.patch，不从包里复制旧部署/任务台账。
- `fractal/`：ZIP SHA256 `b438bb2f0f3a7d0ba47c6ce190dc4876978921524f5010107cebdec2b9c20b29`。包含未提交分型投影候选补丁与完整文件，不含弹窗或算法修复；没有真实浏览器验收。13 个已接收完整文件匹配 manifest。包内 USER_STOPPED 标签属于另一 Agent 的历史停止状态，不能覆盖 Jovi 当前授权。
- `algorithm/`：ZIP SHA256 `03d426aa5b94cdfc26f756bf946436db86ee19fc3f9256d644a776985ced17b7`。7 个已接收材料匹配原 SHA 清单。原始日志、完整 XML 和冗余台账未导入；继承测试总数保存在 INTAKE_SUMMARY.json，不冒充本轮测试。
- `algorithm/LOCAL_REPRO_20261004.json` 是本轮独立离线预测复现结果；运行使用内存替身、禁用 env 文件与网络，无生产操作。

## 已独立确认的缺陷（不是待证明的猜测）

### A. RSI 与传播链

80 根合法 OHLCV，close=1…80：基础结果 frame RSI14=50 / values RSI14、RSI6=50；v05 frame RSI14=100，但 values RSI14、RSI6仍为50。下降序列均0；恒定序列当前约定50。v05沿用错误 base.values 与先前评分。

关键文件：utils/indicators.py、utils/indicators_v05.py、utils/advanced_indicators.py、services/indicator_service.py、utils/strategy_engine.py、services/signal_grade_service.py、services/signal_center_service.py、workspace/chart.py、workspace/read_model.py、services/decision_board_service.py。

图表也调用基础实现，不能声称线上图表已经是100。修复必须统一 RSI6/12/14 的公式、最终 frame、scalar、评分理由、持久化和 API/图表，不能只同步 v05 的单一 RSI14。涨/跌/恒定/暖机/缺失与非有限值规则要明文冻结。TA-Lib 的平盘和初始化约定与项目约定可能不同，需记录定义差异，不盲目修改所有结果。当前版本 ind-v0.7.3-audit / feature-store-v0.7.3-input-mask；公式/初始化变化必须升级版本及相关缓存/读取合同，隔离旧结果。

### B. 支撑压力输入合同

SupportResistanceService._sr_frame 只有 OHLCV/amount，compute直接调用build_support_resistance；MA5/10/20/30/60、BOLL、TD9、MACD/KDJ/RSI确认分支因缺列跳过。250根趋势加正弦数据，经 calculate_indicators 后同一 builder 出现上述全部方法。ATR本身已有OHLC回退，不能把它说成缺失。

图表路径 chart.py → candle_periods.chart_studies 已先生成指标；不能说所有图表都漏算。统一输入、复权、截止、暖机、时间周期和配置，再比方法贡献/levels/ATR。特别比较非默认配置；图表当前使用默认 builder 参数，持久化使用 self.config。日线与周/月数据不是天然等价输入。

关键文件：services/support_resistance_service.py、utils/support_resistance.py、workspace/candle_periods.py、workspace/chart.py。增加指标会改变方法贡献与聚类，必须升级 METHOD_VERSION/派生输入身份，保留旧快照，GET不能自动重建。

### C. 三项预测/校准缺陷

本轮独立重跑接手包离线脚本，均复现：

1. 可选全市场研究：市场日历 purge 与逐标的第N条记录标签结束不一致；缺交易日的资产在1/3/5/10期限出现训练 label_end 进入测试期。涉及 factor_analysis_service.py、global_model_research_service.py、utils/time_split.py。需要显式 label_end_date，并按每条标签结束时点 purge/embargo。
2. validation_service._frames 的原始价格/缺量额填0，与正式 forecast_service 的 history_issues/research_history_rows 合同不一致。合成拆分5条观测收益为 -0.6666666667 对 0；不是真实 ETF 收益。正式模型和验证器应复用输入、公司行动、缺失值与 PIT 合同，冻结输入/配置/代码身份。
3. calibration_service 可将旧报告关联当前配置，只含h1、无独立holdout、mock报告仍在内存候选审批通过；NaN指标的门禁也通过。要求原报告配置/代码/数据哈希绑定、各正式期限、真实来源/PIT、独立holdout和有限值严格验证；审批时重算。默认run_id缺uuid4另有低风险NameError，主TaskService显式run_id不受此错误影响。

这些问题出现在研究/验证/校准路径，不表示正式输出已经错误标记 calibrated；当前正式输出仍not_calibrated/actionable=false，修复期间保持。

## 用户必须得到的交互

- 每个可见K线入口：点击紧凑图表本身必须打开真正的大弹窗，同时提供可访问的放大按钮；仅有按钮不算满足要求；不是浏览器 Fullscreen API。覆盖 Detail、Overview 指数、搜索进入详情、仍可访问的 Legacy detailOverlay/chartCanvas。
- 弹窗以蜡烛主绘图区为主；验收实际主pane高度，不能只量整个540px容器。当前默认多个副图挤占高度，需要减少默认占用，低频选项收起。
- 主操作明确保留一个“显示支撑／压力”，技术指标选择可直接使用；原始/研究/来源等低频选项不能成为看支撑压力的必经步骤。
- 保留价格口径、raw_overlay_allowed、sr_overlay_allowed、未结算/临时观测等fail-closed边界。无合格数据时说明原因，不能画假线或把近似算法标为严格缠论。
- 键盘打开/Escape/焦点返回、背景滚动锁定、关闭重开、周期切换/resize、桌面与390×844/320px验证；弹窗内部平移/十字光标不能反复触发打开。

主要文件：EtfChart.vue、Detail.vue、Overview.vue、GlobalSearch.vue、chartAdapter.ts、chartStudies.ts、style.css，以及backend/app/static/index.html/app.js的Legacy路径。当前预报卡1/5/20交易日与正式1/3/5/10合同不同，不全局替换；OutlookPanel的最终数据来源也需核对。

## 开源参照和全面审计边界

- TA-Lib 官方 C RSI/ATR/MACD/ADX 与 Python0.6.8对照可作为独立参考：逐项冻结版本、初始化、warmup有效区间、数值容差、MACD柱乘2等约定。MA/BOLL/CCI/WR/ROC/MFI成熟窗既有一致结果不抹去；其他现用指标（KDJ/CMF/RSRS/TD9/OBV等）也需明确公式和测试覆盖。
- CZSC现用精确1.0.1：包含/分型/笔/线段/中枢、前缀因果、重绘/暂定/结算、窗口变更与原始时间映射独立验收。chan_zone_approx、simplified-v1、持久CZSC观测是三个不同算法，不可混为同一计算或互认真理。
- UI参考已维护图表社区的pane高度/resize/price-line和交互模式；现用KLineCharts9.8.12，优先最小实现，不能为了借鉴无理由整库替换。
- 保留NOTICE/许可证；vendor/src不进运行时，不自动克隆manual_review仓库到ECS，不导入来历不明指标或上游凭据。
- 预测不是技术指标值直接映射未来涨跌：需审核真实输入lineage、交易日标签成熟性、标准化仅历史、重叠样本有效数量、purge/embargo、冻结walk-forward/OOS与独立holdout、基准/费用/滑点/覆盖率。机制修复及合成测试不等于真实预测可靠；缺PIT/合法数据时明确资格UNKNOWN。

官方参照：
https://github.com/TA-Lib/ta-lib/blob/main/src/ta_func/ta_RSI.c
https://github.com/TA-Lib/ta-lib/blob/main/LICENSE
https://github.com/waditu/czsc
https://tradingview.github.io/lightweight-charts/docs/api/interfaces/ChartOptionsBase
https://tradingview.github.io/lightweight-charts/tutorials/how_to/price-line

## 本阶段交付流程（远端必须实际执行）

1. 从当前origin/main创建有界修复分支，先核对已提供事实、材料哈希和真实GitHub写入/执行能力；不能以只读连接冒充提交。
2. 制定一个完整但有界的阶段计划和失败回归，远端执行RSI/SR/预测硬门槛修复及Modal主交互；审查未提交分型候选，可选取有效投影代码，但不复制其旧台账。
3. 完成现用指标/缠论/预测审计矩阵，把confirmed bug、定义差异、未验数据/统计资格分开。自定义规则不得静默当标准规则；资格门槛不调低。
4. 远端独立审核后提交真实GitHub代码和tests/receipt，给分支/完整SHA/文件范围/实际测试/未完成门槛，禁止只交一段apply脚本或口头“完成”。
5. 本地接收精确SHA到隔离工作树，执行新失败回归、必要完整pytest、compileall/Node、Vue/typecheck/build与真实浏览器/弹窗/图层验证；回传真实GitHub收据或修复。
6. 远端审核本地结果，并制定/实际执行下一阶段已授权的代码任务；生产发布、真实数据采购/权限、策略封版与校准人审仍独立，不自动获得PASS。

本地当前未修改业务代码、未套用候选补丁、未修改生产。当前结果是接手与离线复现，不是修复完成。

