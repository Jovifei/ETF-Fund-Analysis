> **历史基础合同保留**：本文描述旧 main 基础或历史路线；本次 Vue/P0–P4 新增实现、实际测试与未完成项以 [DELIVERY_P0_P4.md](DELIVERY_P0_P4.md) 为准。算法真实性/安全限制继续有效。

# 项目总交接：目标、来龙去脉、实现路径与当前卡点

更新时间：2026-09-06  
面向：后续 ChatGPT / Codex / Claude / 本地 Agent 接手  
当前 main 基线：以 `git rev-parse origin/main` 为准；本轮梳理时主线已完成 v0.8.0 与 v0.8.1 导航合同收敛。

> 重要说明：用户提供的 ChatGPT share 链接 `6a9cd43a-0a04-83e8-b5f8-c0ba299ff3f1` 在本轮自动抓取环境中返回 cache miss，无法直接读取动态共享页。因此本文**不宣称逐字读取了该共享聊天**。项目脉络由当前项目会话上下文、Git 提交历史、`docs/` 既有方案/发布记录和当前代码合同交叉重建。后续如能人工导出共享聊天，应只用来补充动机细节，不得反向覆盖已经由 main+测试确立的事实。

---

## 1. 一句话说清楚最终目标

这不是一个“展示 ETF 行情的网站”，而是一个**个人私有、可审计、每天围绕 14:30 做中国场内 ETF/LOF 研究决策的系统**：

> 从板块找机会 → 选 ETF → 结合持仓成本、自选、技术指标、量能/资金、支撑压力、新闻和 1/3/5/10 日预测 → 在 14:30 得到一个统一、可解释、可回溯的五档研究动作：`可加仓 / 可入场 / 可试探 / 观望 / 减仓`。

系统必须同时满足三个约束：

1. **数据真实**：没有实时/合格数据时宁可显示 unavailable/degraded，也不能用 Mock、静态快照或日 K 冒充实时/分钟数据。
2. **计算单一权威**：MACD/KDJ/RSI/指标、预测、当前动作由后端确定性逻辑/持久化快照给出；AI 和前端只解释/展示，不能产生第二套动作。
3. **研究而非自动交易**：不接券商、不自动下单、不把预测写成确定收益；未完成真实样本外验证前保持 research-only / not_calibrated。

---

## 2. 用户真正想解决的日常问题

用户的核心使用场景可以按一天拆成四步：

### A. 找机会
- 看行业/概念板块谁强谁弱；
- 看板块今日表现、上涨/下跌家数、轮动强度；
- 找到板块对应的主导/高弹性 ETF。

### B. 看自己的标的
- 把 ETF 加入自选；
- 录入持仓份额、成本价、目标权重；
- 看到现价、盈亏、当前动作，以及多个预测期限。

### C. 深入研判单只 ETF
- 任意页面点击 ETF 都进入同一个 `/etf/{code}`；
- 看历史 K 线、支撑/压力 Zone、MA/MACD/KDJ/RSI/TD9 等；
- 看 1/3/5/10 日研究预测和未来情景走廊；
- 看与该 ETF/主题相关的新闻和风险证据；
- 有持仓时应结合成本线理解风险收益。

### D. 14:30 做最终研究判断
- 14:30 是“决策”的二级模式，不是另一个产品；
- 当前语义路由为 `/decision/1430`；
- 输出必须使用与其他页面同一 current action，不允许 14:30 自己算另一套“买入候选/回避”。

---

## 3. 项目如何一步步走到现在

### 阶段 0：先建立“研究系统”而不是“AI 炒股机器人”
最早底线被明确为：

- 指标、信号、回测是确定性 Python；
- AI 只做结构化新闻/证据解读；
- 不连接券商；
- Mock 只用于测试/演示；
- 数据来源、时间、质量必须可审计；
- 修改策略必须版本化，并经过 walk-forward、事件回测、泄漏检查和人工批准。

这形成了 `AGENTS.md` 的长期契约，后续任何“页面更好看”“预测更大胆”的要求都不能突破它。

### 阶段 1：把基础数据、指标、预测、信号、持仓、审计跑起来
核心能力逐步建立：

- FastAPI + PostgreSQL + Alembic；
- Provider Adapter（Tushare / AKShare / composite / Mock）；
- 日线/行情/市场上下文；
- IndicatorSnapshot / ForecastSnapshot / SignalSnapshot；
- 持仓、报告、审计、任务、SSE；
- 可选 LLM 分析网关；
- 本地 OCR 持仓截图候选复核流程。

这一阶段最大的教训是：**代码存在不等于生产有数据**。曾出现 scheduler 未启用、provider 仍是 mock，导致“页面没数据”；随后才把免费真实源、K 线降级链、板块数据、指数上下文真正跑通。

### 阶段 2：开源工程调研，确定“借鉴设计、核心独立实现”
调研结论是没有一个开源项目能同时满足中国 ETF/LOF、稳定数据源、指标/新闻/预测、私有 Web、阿里云生产与审计要求，所以选择拼装思想而不 import 对方运行时代码。

具体借鉴见第 6 节。

### 阶段 3：建立 WorkBuddy 风格的决策看板
用户希望决策页更像一个“看一眼就知道强弱、原因和下一步”的专业看板，而不是工程控制台。

形成了 `decision_board_workbuddy.*`：

- 五档分组；
- 强弱颜色；
- KDJ J 值、MACD、RSI、量能解释；
- 预测置信度解释；
- 明确数据源/时间/退化状态；
- 点击 ETF 看详情。

这一阶段曾有“前端研究评分”实验，但后来证明会制造第二口径，因此 v0.8 收敛时废除，服务端成为唯一权威。

### 阶段 4：构建 14:30 工作台
14:30 工作台将趋势、动量、量能资金、结构/支撑压力、预测、新闻整合成尾盘研究候选；同时建立：

- 1/3/5/10 日预测；
- 支撑压力多方法聚类；
- 历史 + 未来情景蜡烛；
- point-in-time 数据集构建器；
- 14:20–14:40 资格窗口；
- 明确 `historical_1430_backtest=not_qualified` 的验证边界。

问题也从这里暴露：14:30、K线页、综合页、WorkBuddy 页逐渐变成多个平行产品，且部分服务重复计算同一指标/支撑压力。

### 阶段 5：多 AI 审计后做 v0.8.0 架构收敛
三份独立 AI 方案最终达成一致：真正的问题不是功能少，而是**页面、计算、入口和口径过多**。

重构重点：

1. 清除假数据和默认邀请码；
2. 指标状态唯一来源；
3. 支撑压力统一快照；
4. current action 唯一来源；
5. 建立全局 ETF 详情 `/etf/{code}`；
6. 建立 `/boards`；
7. 建立用户 watchlist；
8. 引入 MarketBar 多周期底座；
9. 新闻解释来源分层；
10. 退休独立 Kline 全市场页。

v0.8.0 以 705 passed / 3 skipped 和生产迁移/部署记录完成发布。

### 阶段 6：v0.8.1 导航再次收敛
v0.8.0 发布后用户仍感觉“点击和页面切换逻辑混乱”。原因是语义已经收敛，但老 URL / legacy 壳仍影响使用心智。

最终导航合同调整为：

- `/` → 决策；
- `/boards` → 板块；
- `/holdings` → 持仓；
- `/research` → 研究；
- `/research/news` → 新闻证据；
- `/system` → 系统；
- `/decision/1430` → 决策的 14:30 二级模式；
- `/etf/{code}` → 全局唯一 ETF 详情。

旧 `/legacy`、`/workbench/1430` 等只保留兼容重定向/书签兼容。

---

## 4. 每一步实现时必须遵守的要求

### 4.1 数据层
- 外部数据必须经 Provider Adapter；业务层不硬编码网页接口。
- 保存 source、source timestamp、fetched_at、verification/freshness/degraded reason。
- Mock、stale、unverified、missing 核心字段必须降低/阻断 actionable。
- 日 K 绝不能冒充 30m/60m/5m/15m。

### 4.2 指标层
- MACD/KDJ/RSI/MA/TD9/量能等以持久化 IndicatorSnapshot/统一状态函数为权威；
- 页面请求不能再自行从全量历史重算一套不同参数；
- 指标公式变更必须升级版本并验证。

### 4.3 current action
- 全系统同一 ETF 同一时刻只能有一个 canonical current action；
- 任何研究评分、Signal Center 系数、14:30 排名分都只能解释/排序，不能覆写 canonical action。

### 4.4 支撑压力
- 同一 ETF 不同页面必须读取同一 SupportResistanceSnapshot；
- 支撑压力显示为 Zone（上下界），不是把震荡区强行压成单一精确价格；
- TD9/KDJ/MACD 等只能用真实价格事件确认 Zone，不能把振荡器数值直接当价格。

### 4.5 预测
当前正式研究期限合同是 `1/3/5/10` 交易日。

- 未校准：只能写“历史相似样本上涨占比/研究情景”；
- calibrated：只有通过相应验证和人工批准后才允许写“上涨概率”；
- 未来蜡烛必须标记 `is_forecast=true` / `not_actual=true`；
- 14:30 的 provisional 当日状态不能污染以收盘日线为邻居的 EOD 预测基准。

### 4.6 AI
- AI 不计算指标、预测、仓位或 current action；
- 只解读已生成的证据包；
- 不静默切模型/Provider；
- 不拥有数据库写权限、网络抓取能力、Shell 或券商权限。

### 4.7 前端
- 页面展示后端权威结果，不创建第二套 score/action；
- 每个用户任务一个稳定入口；
- 任意 ETF 点击统一去 `/etf/{code}`；
- 错误态必须显式，不用静态数据“让页面看起来正常”。

### 4.8 生产
- PostgreSQL + Alembic；
- 先备份、后迁移、再 smoke；
- `git pull --ff-only`；
- 生产 secrets 不进 Git/聊天/文档；
- API/scheduler/provider audit 都要检查；
- 失败可回滚，不静默降级。

---

## 5. 当前页面的正确心智模型

| 用户任务 | 当前路由 | 应该做什么 | 不应该做什么 |
|---|---|---|---|
| 决策 | `/` | 看全池五档、当日变化、预测与风险 | 再做一套本页特有 action |
| 板块 | `/boards` | 找行业/概念机会、ETF 代理 | 把 ETF 代理涨跌冒充板块指数 |
| 持仓 | `/holdings` | 看个人成本/盈亏/动作/预测/自选 | 混入其他用户持仓 |
| 研究 | `/research` | 信号归因、深层研究 | 变成第二个“决策首页” |
| 新闻 | `/research/news` | 看新闻事实、启发式/AI 来源 | 把 AI 推断当事实 |
| 系统 | `/system` | 数据源、任务、账户和审计 | 暴露给不该管理的用户 |
| 14:30 | `/decision/1430` | 决策的尾盘研究模式 | 生成另一套 action 体系 |
| ETF 详情 | `/etf/{code}` | 单标的 K线/Zone/预测/指标/新闻 | 每个页面各维护自己的详情弹层 |

---

## 6. 页面、组件和开源项目到底借鉴了谁

### 6.1 WorkBuddy：信息架构/视觉优先级参考
借鉴的是：

- “评分/强弱一眼可见”；
- 颜色具有明确语义；
- 指标解释紧贴数值；
- 预测期限与置信度直接展示；
- 数据来源、时效、风险必须可见；
- 宽表按动作分组。

**不是像素级复制。** 历史文档明确记录：自动环境当时也无法读取 WorkBuddy 动态分享页，因此实现依赖用户描述、已有截图/上下文和本项目数据合同。

### 6.2 illusionno/fund-analysis-matrix：暗色金融卡片 + 点击标的详情
借鉴：

- 暗色基金/股票卡片；
- 自选先 hydrate 再刷新；
- 点击标的打开 K 线详情；
- BFF 隔离浏览器和第三方数据源。

没有直接采用其 React/Vite 运行时；本项目为了个人 ECS 简化，主要使用原生 JS/CSS。

### 6.3 thincat75/fund-rotation-analyst：流水线与证据审计
借鉴：采集→分析→渲染→校验四段式、provider/质量哈希、主题 taxonomy、LLM 只解释证据。

### 6.4 simonlin1212/vibe-astock：先验证输入，再出结论
借鉴：Preflight、降级醒目标识、结构化 AI 输出、安全失败、信号过期时间。

### 6.5 zhangsensen/etf-rotation-strategy：策略验证思路
借鉴：WFO→向量化→事件驱动审计、迟滞、风险门控、参数冻结、因子方向元数据。

### 6.6 TradingAgents-CN：系统分层
只借鉴 provider/模型配置、FastAPI/DB/缓存/前端/Docker 分层和任务状态；没有复制受限制源码。

### 6.7 Qlib / AKQuant：下一阶段研究验证方法
用于 factor / walk-forward / 高级模型研究参考，不替代当前数据审计底座。

### 6.8 KLineChart / ECharts / TradingView Lightweight Charts：图表候选，不是当前运行依赖
Master Plan 曾倾向 Lightweight Charts；但实际 v0.8.0 选择了**自绘 Canvas**，并已经实现滚轮缩放、拖拽平移、双击复位、十字光标、Zone、预测情景。

因此后续 Agent **不得仅因为 Master Plan 写过 Lightweight Charts 就重写图表**。只有当现有 Canvas 出现明确维护/性能/交互问题，才单独评估替换收益。

---

## 7. 颜色和组件必须遵守什么

当前设计不是“抄某一个项目的颜色表”，而是三层约束叠加：

1. **中国行情习惯**：上涨/偏强用红/暖色系，下跌/风险用绿（与欧美 red=down 不同）；
2. **WorkBuddy 式语义清晰**：分组、指标、状态、置信度用明确颜色层级；
3. **暗色专业金融界面**：参考 fund-analysis-matrix 的暗色卡片/表格密度。

详细规则见 `UI_UX_CONTRACT.md`。

---

## 8. 哪些地方曾经卡住

### 数据没进库
不是“页面 bug”，而是 scheduler/provider 配置仍停留在 mock/disabled。解决方式是先做 Provider 能力矩阵与真实灌数。

### 东财部分接口反爬断连
解决方式不是在业务层硬爬，而是 AKShare adapter 内建立新浪/同花顺等可审计降级链；无法取得的字段诚实显示不可用。

### 多页面重复计算/重复动作
Kline/14:30/Signal Center/WorkBuddy 曾各自有局部语义。v0.8 通过 current action 唯一来源、IndicatorSnapshot、SupportResistanceSnapshot 和统一 ETF 详情收敛。

### 导航仍混乱
即使 v0.8.0 逻辑已统一，`/legacy`、`/workbench/*` 和多个详情入口仍造成心智负担。v0.8.1 继续按用户任务收敛为 Decision / Boards / Holdings / Research + `/decision/1430`。

### 计划和实现分叉
Master Plan 建议 Lightweight Charts、20D、`/portfolio` 等；实际代码因部署复杂度、已有合同和验证边界选择了 Canvas、1/3/5/10、`/holdings`。后续必须记录“为什么不同”，不能把差异误判成代码遗漏。

---

## 9. 离“最终完成”还差什么

### A. 最大硬阻塞：真实 14:30 point-in-time 验证
目前系统功能上能给出 14:30 研究结果，但还没有证据证明“14:30 做这个判断在真实交易条件下有效”。必须补：

- 真实 5/15 分钟历史数据（或更高质量 point-in-time 数据）；
- 特征截止严格到 14:30；
- 14:30 后第一条可成交价格；
- 费用、滑点、涨跌停/停牌/溢价等约束；
- 最近 6–12 个月隔离 Holdout；
- rolling/purged walk-forward；
- shadow run，不下单；
- 人工批准。

在此之前 `historical_1430_backtest` 必须保持 `not_qualified`。

### B. 预测仍未完成真实校准
当前预测用于方向/情景研究，不是 calibrated probability。需要对 1/3/5/10 各期限做 OOS：

- Brier；
- direction accuracy；
- MAE；
- pinball loss；
- 80%/90% coverage；
- interval width / quantile crossing；
- path-low/path-high coverage；
- support/resistance touch Brier。

### C. 真实分钟 K 线资格仍不足
MarketBar/30m/60m 底座已经有，但生产 provider 的分钟线资格没有完全闭环；未同步时按钮必须继续禁用，不能日线假扮分钟线。

### D. 产品 UI 仍有“壳层技术债”
导航语义已经正确，但当前 `/holdings`、`/research`、`/system` 仍复用 legacy `index.html` 大壳，由 `legacy_route.js` 切模块；`/decision/1430` 仍有自己的 HTML。

最终 UI 收尾可以做：

- 把 Holdings / Research / System 拆成真正独立页面/组件；
- 让 14:30 真正复用 Decision 同一页面组件/状态，而不是只做到“二级 URL”；
- 删除已无用户入口的 legacy dashboard/detail DOM。

这是体验/维护性债，不是当前数据可信度的最大阻塞。

### E. 可选增强，不应阻塞核心目标
- 20D/1个月预测：Master Plan 提过，但当前正式合同是 1/3/5/10；只有用户再次确认且完成新 horizon 的 purged WFO 后再启用。
- 韩国半导体可交易代理：当前免费源覆盖不足。
- 概念板块涨跌家数：免费源不完整，可等待更可靠 provider。
- 将 Canvas 换成 Lightweight Charts：只有有明确收益时再做。
- 完整 CZSC：当前仅缠论价格重叠近似；不是原始 14:30 核心目标的必要条件。

---

## 10. 后续 Agent 正确接手顺序

1. 读 `AGENTS.md`；
2. 读 `docs/README.md`；
3. 读本文；
4. 读 `UI_UX_CONTRACT.md`；
5. 读 `ROADMAP_TO_FINAL.md`；
6. 查看当前 `main` 和 CI，不相信旧分支状态；
7. 若要改策略/预测/指标，先确认版本与验证要求；
8. 若只改 UI，不得改变 canonical action、forecast semantics 或数据真实性边界；
9. 先写失败测试/复现，再改代码；
10. PR 通过完整 CI 后再合并/部署。

最重要的一条：**下一阶段不要继续“堆页面和指标”，应该优先把真实 14:30 point-in-time 验证和预测校准做完。**
