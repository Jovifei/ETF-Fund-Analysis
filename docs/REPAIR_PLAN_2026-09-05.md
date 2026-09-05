# ETF 决策系统统一修复方案 v2（页面架构 · 数据一致性 · 安全加固）

版本：v2.0（综合五份审核/方案后定稿）  
日期：2026-09-05  
性质：**方案文档，本轮不实施**。所有修复执行时仍须遵守 AGENTS.md（测试先行、不自动交易、Mock 不冒充真实、不自动改 calibrated、不自动 push）。

综合来源：三份独立审核（产品架构 / 生产运维 / 代码审计）+ 两份外部修复方案（架构重塑方案、修复与落地方案）。本版裁决原则：**产品终态采架构分析、代码债与优先级采代码审计、生产成果采运维排查、工程机制（Presenter/快照表/Watchlist 模型/原子 PR）采两份外部方案的精华**；同时补齐两份外部方案共同缺失的 P0（凭据泄露处置）与 CSP 约束下的图表库选型限定。

---

## 一、产品合同（所有修复必须保护的不变式）

> 本节固化为验收基线：任何 PR 违反以下任一条即打回。

1. **Current Decision 唯一权威**：五档动作只来自 `CurrentDecisionService`（DecisionBoardSnapshot → SignalGradeService → SignalSnapshot 三级回退）。任何页面/组件只**展示** canonical action，禁止按自己的综合分、TD9、新闻或 forecast 另生成一套买卖结论。
2. **Forecast 语义分离**：预测是研究证据，不是第二决策引擎。未校准的 `p_up` 只能表述为「历史相似样本加权上涨占比」；`calibration_status=calibrated` 才可写「上涨概率」。
3. **14:30 时间边界**：14:30 provisional OHLCV 可用于当前报价、盘中临时指标、当前分级、支撑压力与图表；**禁止**将其与历史 EOD 邻居混合计算未来收益预测（在分钟级 point-in-time 历史样本建立之前）。
4. **数据不足 fail-closed**：missing / stale / unverified / degraded / mock / 时间戳不合格 / 核心指标缺失 ⇒ 不生成操作级提示，`actionable=false`。
5. **单一计算权威**：MA/MACD/KDJ/RSI/TD9、形态预测、评分只在后端 Python 计算并落库；前端只做展示格式化，禁止复制任何指标/评分公式。
6. **策略与实盘隔离**：永不连接券商、永不自动下单。

---

## 二、五份材料的裁决摘要

| 来源 | 采纳 | 不采纳/修正 |
|---|---|---|
| 审核一（产品架构） | 四入口信息架构、工作流闭环、持仓+预测融合、区域化支撑压力、20 交易日=1月、新闻分层展示 | — |
| 审核二（生产运维） | 全部生产修复成果固化为不可回退基线（迁移 a3b4c5d6e7f8、板块/新闻补齐、权限、bind mount） | 「四页面长期并存」不作为终态，仅作过渡 |
| 审核三（代码审计） | 全部 12 项问题与优先级；kline 假数据红线；口径冲突；性能债清单 | — |
| 外部方案 A（架构重塑） | 统一指标引擎模块、250 根窗口 + `volume*close` 降级、窗口函数查询、一次性邀请码（增强项）、ocr-worker 容器 | ①遗漏凭据泄露 P0；②分钟线只做前端切换、缺数据层；③图表库引入未标注 CSP 约束；④工期高估（前端重建 3-4 天不现实） |
| 外部方案 B（修复落地） | 产品合同表述、UserWatchlistEntry 与全局 universe 分离、ETFResearchView 统一 Presenter、SupportResistanceSnapshot 快照表、MarketBar 多周期模型、路由迁移表 + deprecated API 兼容、PR-A~E 原子拆分、测试矩阵、验收清单、bind mount 治理 | 篇幅冗余（收敛为本文件）；同样遗漏凭据 P0；REGISTRATION_ENABLED 默认值表述（本版裁定：默认关闭，显式配置邀请码才开放） |

---

## 三、P0 — 立即处置（安全与数据真实性红线）

| # | 事项 | 动作 | 验收标准 |
|---|---|---|---|
| P0-1 | **生产凭据泄露**（生产管理员账户密码已进入聊天与文档） | 立即轮换该账户密码；审计 `auth_sessions` 近期登录记录；检查邀请码/Token 是否同时泄露；此后一切报告/聊天/文档禁止出现凭据 | 密码已换；无可疑活跃会话；`check_no_secrets.py .` 全绿 |
| P0-2 | **注册默认不设防** | 代码层默认 fail-closed：未显式配置 `REGISTRATION_INVITE_CODE` 时注册接口返回 403「未开放注册」（等价 `REGISTRATION_ENABLED=false` 语义）；生产 `.env` 配强随机邀请码 | 空配置时无法注册；测试锁定该行为 |
| P0-3 | **kline 页静态假数据兜底** | 删除 `kline_stabilization.js` 内 STATIC_DATA/SNAPSHOT_ROWS 及回退分支（测试 fixture 可迁往 `backend/tests/fixtures/` 供测试用）；API 失败显示「数据暂不可用 + 最后成功时间 + 重试」，未登录弹登录框；标题去掉「实时」 | 断网/未登录时页面为零行情数据 |
| P0-4 | **指标口径冲突** | 建 `app/indicators/engine` 统一计算内核；kline/1430 服务删除重复的 MA/MACD/KDJ/RSI/TD 现算，改读 `IndicatorSnapshot`；确需盘中增量的统一走 engine 且初始化口径与落库一致 | 同一 ETF 同一时刻跨页面指标值差 < 1e-6（单测锁定） |
| P0-5 | **支撑/压力输入不一致** | 全系统唯一入口 `build_support_resistance`：统一回溯窗口（默认 250 交易日，config 化）、真实 `amount`（缺失时降级 `volume*close` 并标注）；短期由单一 Service 封装调用，中期落 SupportResistanceSnapshot（见 §5.3） | 跨页面 support/resistance 完全一致（单测锁定） |
| P0-6 | **前端死代码 Bearer + 文案** | 移除 `localStorage fundDecisionToken` 路径；全站统一「退出登录」；kline 死代码随 P1-3 详情化一并清理 | 全局 grep 无 localStorage token 读写 |

---

## 四、终态信息架构与路由迁移

### 4.1 目标导航（普通用户 4 入口 + 管理员 1 入口）

```text
🎯 决策      /            五档分组 + 排名双视图；模式：盘中 / 14:30尾盘 / 收盘复盘
🔥 行业板块  /boards      板块强度矩阵（行业/概念分栏、标注 ETF-proxy 语义）→ 成员 ETF
💼 我的持仓  /holdings    份额/成本/现价/盈亏 + canonical action + 1/3/5/10(/20)日预测列 + 距支撑/压力
🔬 研究中心  /research    市场环境、7×24 新闻、信号中心、因子报告、演示模式
⚙ 系统      /system      管理员：标的池、Provider 探针、任务调度、用户管理
📈 ETF 详情  /etf/{code}  全局唯一详情研判台（任何列表点击进入）
```

**14:30 模式独有信息**：决策窗口 14:20–14:40、目标时刻、快照时间、报价资格（source time verified）、风险收益比、与上一 slot 的变化、持仓优先提示。**不再重复**：另一套总表/另一套 K 线/另一套评分公式。

### 4.2 路由迁移表（旧 URL 全部 307 到新语义入口）

| 旧 | 新 |
|---|---|
| `/`（workbuddy 决策台） | `/`（新版决策总览） |
| `/legacy` | `/research` |
| `/workbench/1430` | `/decision?mode=1430` → 实现为 `/` 的模式参数 |
| `/workbench/kline`（?code=…） | `/etf/{code}` |
| `/assets/*.html` 直链 | 对应新路由 |

**兼容原则**：旧 API（`/api/workbench/1430/*`、`/api/workbench/kline/*`、`/api/decision-board*`）**不立即删除**——内部改为调用统一 Presenter，响应加 `deprecated=true` 字段，前端迁移完成后再下线。

---

## 五、统一计算与展示层（消除多页面漂移的机制）

### 5.1 ETFResearchViewService（统一 Presenter）

一个只读聚合服务输出统一 schema，所有页面复用：

```text
identity / quote / holding / current_decision /
indicator / forecasts / support_resistance /
sector / news / data_health / provenance
```

- 决策页、板块页、持仓页、ETF 详情、14:30 模式、信号中心全部消费同一 schema；
- presenter 只做快照读取与格式拼装，**不做指标计算**（读 IndicatorSnapshot / ForecastSnapshot / SupportResistanceSnapshot）；
- 这是「跨页面数值一致」的制度性保证，而非靠约定。

### 5.2 指标引擎（app/indicators/engine）

- 落库链保持：IndicatorService（收盘）→ IndicatorSnapshot；
- 盘中临时需求（provisional 状态）由 engine 基于日线+最新报价轻量推导，初始化口径与落库完全一致（同一函数、同一参数）；
- kline/1430 的自有实现全部删除（对应问题清单 #4）。

### 5.3 SupportResistanceSnapshot（新增表，方案 B 精华）

```text
instrument_id / interval / as_of_time / current_price /
levels_json(zone 化) / method_version / feature_schema_version /
config_hash / source_cutoff / generated_at
```

价值：① 消除每请求重复计算（性能）；② 输入 cutoff 统一（一致性）；③ **14:30 时点的支撑压力可完整回放**（审计与未来 14:30 回测的基础）。盘中 14:20/14:30/14:40 槽位随决策快照一并落盘。

### 5.4 支撑压力「区域」模型

level 升级为 zone：`center_price / zone_low / zone_high / strength / methods / confirmations / basis_time / interval`。区域宽度可由 cluster_tolerance、ATR 或方法自带区间推导，必须可审计。前端半透明矩形渲染：绿=支撑、红=压力、蓝=forecast corridor、黄=用户成本线、紫=缠论近似（永远标注「近似」，完整 CZSC 对账完成前不得称「中枢」）。

### 5.5 前端评分处理（裁定：方案 A）

服务端生成 `research_score / research_components / score_semantics="ranking_only_not_current_decision"`，前端只展示；删除 workbuddy JS 全部打分函数（scoreRow/maScore/macdScore/…）。UI 明示「仅用于同档内排序，不改变五档」。

---

## 六、功能补全（按用户工作流排序）

### 6.1 行业板块一等页（/boards）

- 数据基础已有（BoardService + 266 板块快照）；新增聚合端点 `/api/sectors/market`（今日/5日/20日、涨跌家数、广度、主 ETF、企稳评分、跨板块排序）。
- **语义标注**：区分「板块真实/公开市场数据」与「ETF 代理状态」，UI 不得把 ETF proxy 评分当真实行业指数涨跌。
- 点击板块 → 成员 ETF（含五档 + 预测摘要）→ 「加关注 / 深入研判」。

### 6.2 用户添加 ETF（UserWatchlistEntry，采方案 B 设计）

**关键修正**（相比我 v1 的「直接建 Instrument」）：把**系统 universe** 与**用户关注**分离。

- 新表 `user_watchlist_entries(user_id, ts_code, created_at, note)`；
- 流程：输入 `159915` / `159915.SZ` → 服务端经 Provider Adapter 查名称/交易所（禁止前端直连行情站）→ 用户确认 → 写入用户关注；可选「立即录入持仓」（份额/成本）；
- 用户的关注标的若不在全局 Instrument 表：自动创建 Instrument（enabled=true，主题按 universe_theme_rules 分类）并触发异步初始化（日线/指标/预测管线）；创建动作记审计（user_id）；
- 管理员可在系统页把用户关注提升为正式池成员。

### 6.3 我的持仓（/holdings）

每行：份额/成本/现价/浮盈/盈亏% + **canonical action** + 1/3/5/10(/20)日预测列 + 当前价距最近支撑/压力 + 成本线（进详情图）。全部读既有快照，不新增计算。持仓标的在决策页默认置顶分组。

### 6.4 ETF 详情（/etf/{code}，全站核心页面）

- **顶部摘要**：名称/代码/主题、现价、今日、canonical action、我的成本与盈亏（如有持仓）、数据源与 source/snapshot 时间；
- **预测期限结构同列**：1/3/5/10（/20）日各列 = expected return + q10/q50/q90 + conf + 校准状态 + sample_count + as_of_date + feature_basis；**取消下拉框**；
- **多周期 K 线**：30m / 60m / 日K（数据层见 6.5）；
- **交互**：滚轮缩放、拖拽平移、十字光标、双击复位、可见区间管理；
- **指标联动**：综合 / MA / MACD / KDJ / TD9 / RSI / 缠论近似 / 成交密集——点击某指标只渲染该 methods 的支撑/压力**区域**与趋势线；
- **叠加层**：预测 corridor（q10/q50/q90 半透明带 + cutoff 垂直虚线 + 「预测情景·非实际」标注）、用户成本线、快照标记、14:30 标记；
- **TD9 价格位**：新增 level method——统计历史 TD sell/buy setup 8/9 触发后经确认反转的高/低点并聚类；**TD9 数字不得直接变价格线**。

### 6.5 分钟线数据层（MarketBar/IntradayBar）

- 新表（方案 B 模型）：`instrument_id / interval(5m,15m,30m,60m,1d) / bar_time / OHLCV / amount / source / source_timestamp / timestamp_verified / fetched_at`；唯一键 (instrument, interval, bar_time)；
- Provider Adapter 走 AKShare 分钟接口（30m/60m 优先），调度器盘中增量拉取，时间戳资格门控与实时报价同规则；
- **第一阶段只开放 30m/60m/日K**；分钟数据未落库时前端周期按钮禁用——**日 K 永不冒充分钟线**；
- 存量 DailyBar 保留，不强行迁移（可后续统一）。

### 6.6 20 交易日（1 个月）预测

- horizon contract 正式扩展为 1/3/5/10/20（20 交易日≈1 个月）；**不复活旧 20 日 fallback 快照**；
- 完整研究门槛：forward-return target → purge → expanding walk-forward → OOS 方向准确率/Brier/pinball → 80%/90% coverage → 置信校准 → PIT provenance → 人工批准；未达标 UI 显示「1个月：研究中」；
- 通过后进入全部展示位（决策列/持仓列/详情 corridor）。

### 6.7 新闻展示层

- 获取链保持：东方财富 7×24 → 财联社 fallback → 可选 RSS/RSSHub（统一 NewsRecord 适配）；
- 解析两层：确定性层（去重/时间/ThemeClassifier/关键词情绪/impact/risk_flags，永远运行）+ 模型层（ANALYSIS_ENABLED=true 时，带 provider/model/prompt/schema/input_hash provenance）；
- UI 升级：新闻卡片分区展示「事实 / 规则解读 / AI 深度解读（若存在）/ 风险 / 影响方向与期限」，**必须标明是规则分析还是模型分析**；新闻权重维持 5%（解释与风险修正，不直接翻转 canonical action）。

---

## 七、性能与调度

| # | 事项 | 方案 |
|---|---|---|
| O-1 | 1430 summary/detail 每请求全量重算 | 改读统一 Presenter + SupportResistanceSnapshot；盘中仅增量补报价字段；目标快照命中路径 < 300ms |
| O-2 | `_latest_forecasts` 全量拉历史行 | 窗口函数 / DISTINCT ON (instrument_id, horizon) + 索引 (instrument_id, horizon, as_of_date DESC, generated_at DESC)；所有 service 统一改用 |
| O-3 | CurrentDecisionService 全表扫 SignalSnapshot | 同 O-2 模式（max(as_of_time) per instrument） |
| O-4 | 调度槽位收敛（当前代码 19 槽与 scheduler 8 槽两处定义，先核对统一） | 建议终值：常规 09:35 / 10:30 / 11:15 / 13:15 / 14:00；**尾盘加密 14:20 / 14:30 / 14:35 / 14:40 / 14:50**；收盘 15:00；盘后结算 15:30。Quote 保持 3 分钟独立节流；最终以实测服务器成本微调 |
| O-5 | 刷新机制三页三样 | 全站统一「SSE 事件驱动 + 槽位快照」；决策/板块/持仓/详情统一监听 `decision_board.updated` 等；14:30 页接入 SSE 后去掉手动刷新依赖 |
| O-6 | 100+/300 标的压测 | 上池前后各一轮：页面读请求 P95、14:30 快照生成窗口、DB 随历史增长不线性恶化 |

---

## 八、运维与部署固化（不可回退基线 + 治理决策）

| # | 事项 | 状态 | 动作 |
|---|---|---|---|
| D-1 | forecast_version 列 String(64)（迁移 a3b4c5d6e7f8） | 已做 | 确认迁移入库 + ORM 长度断言测试防回退 |
| D-2 | scheduler 收盘链补 sector/board 刷新 | 已做 | 补 after_close 顺序回归测试 |
| D-3 | AKShare 新闻（东财→财联社） | 已做 | 保留；离线单测不触网 |
| D-4 | reports 目录权限 + 非 root 容器 | 已做 | 写入 docs/ALIYUN_DEPLOYMENT.md 部署检查单 |
| D-5 | **backend bind mount 治理**（./backend:/app/backend:ro） | 已做待决策 | 二选一并写明：生产=immutable image（代码烧进镜像，易回滚/审计）；灰度开发机=bind mount。禁止长期处于「git checkout 与镜像内容不一致且无法确定运行版本」状态 |
| D-6 | OCR 生产关闭 | 保持 | 启用路径：独立 `ocr-worker` 容器 + 模型只读卷 + 版本固定，与主 API 隔离；默认 disabled 永远是安全态 |
| D-7 | ANALYSIS_ENABLED | 默认关 | 配 Key 时服务器本地 .env；新闻 UI 按 §6.7 切换 |
| D-8 | 307 重定向 | 已做（临时） | IA 收敛完成后改为 §4.2 迁移表 |
| D-9 | 增强项（可选） | 未做 | 管理端一次性邀请码（限次数/有效期）替代静态邀请码 |

---

## 九、实施路线图（原子 PR 序列）

> 原则：先安全、再口径、再收敛、再功能；每个 PR 独立可回滚、带测试；批次门禁全过才进下一批。**不自动 push/合并**，批次边界向用户汇报。

```text
PR-A  真实性与安全（P0 全部，1-2 天）
      删 kline 静态 fallback（fixture 迁测试目录）；注册 fail-closed；
      凭据轮换与审计；删 localStorage Bearer；统一退出文案；数据错误态组件
      门禁：pytest + secret scan + 断网 smoke

PR-B  统一计算与展示层（P0-4/5 + §5，3-5 天）
      app/indicators/engine；kline/1430 去重算；
      支撑压力统一入口 + SupportResistanceSnapshot 表与回填；
      ETFResearchViewService 与统一 schema；latest 查询 SQL 优化（O-2/O-3）
      门禁：跨页面一致性测试（同 ETF 同时刻 action/指标/支撑压力全等）

PR-C  页面信息架构收敛（§4，5-8 天）
      新 App Shell（决策/板块/持仓/研究/系统）；ETF 详情组件抽取（/etf/{code}）；
      14:30 变模式；宽度三列迁入详情；旧路由 307 + API deprecated 标记；
      命名统一（一页一名）
      门禁：四尺寸 smoke + 旧链接跳转测试 + 「企稳/K线企稳」字样清零

PR-D  持仓 + Watchlist（§6.2/6.3，3-4 天）
      user_watchlist_entries；添加 ETF 流程（Provider 查询→确认→关注→持仓）；
      持仓页预测列 + canonical action + 距支撑压力；成本线进详情
      门禁：多用户隔离测试 + 无管理员自助走通「添加→关注→持仓→盈亏→预测→K线」

PR-E  行业板块一等页（§6.1，2-3 天）
      /api/sectors/market 聚合 + /boards 页 + 成员穿透 + proxy 语义标注
      门禁：板块→ETF→详情链路 smoke

PR-F  图表引擎与区域系统（§5.4/6.4，5-8 天）
      技术验证 spike（自研 viewport 状态机 vs vendor 化 Lightweight Charts——
      CSP script-src 'self'，第三方库必须 dist 文件入 static/ 并锁版本，
      禁 CDN/运行时拉取）；zoom/pan/crosshair；zone 化渲染；
      method 过滤联动；TD9 level method；forecast corridor 带
      门禁：图表交互测试 + TD9 不得直接变价格线的实现审查

PR-G  分钟线管线（§6.5，4-6 天）
      MarketBar 表 + AKShare 分钟 Adapter + 盘中增量调度 + 30m/60m/日K 切换
      门禁：日K不冒充分钟线测试 + 时间戳门控测试

PR-H  20 日预测（§6.6，与 PR-G 并行，研究周期 1-2 周）
      horizon=20 全管线 + 门槛报告 + 人工批准后才上 UI
      门禁：walk-forward 报告 + 人工批准记录

PR-I  新闻展示 + 收尾（§6.7 + kline 下线 + legacy 瘦身，2-3 天）
      门禁：全量回归 + 四尺寸 smoke + 验收清单勾平
```

关键顺序约束（方案 B 精华）：**不要先做漂亮图表再解决数据口径；不要先加 20 日预测再解决多页面计算不一致。** PR-B 必须先于 PR-F/H。

---

## 十、测试矩阵（每批次按相关项执行）

- **数据真实性**：API down 不显示 fixture；stale/unverified/missing/mock 各态；provider 降级；source timestamp 门控
- **跨页面一致性**：同一 ETF 在决策/板块/持仓/研究/详情/14:30 模式下 current_decision、forecast、indicator、support/resistance、provenance 全等
- **持仓**：自助添加 ETF、手工录入、OCR（低置信/重复/更新/删除）、多用户隔离、盈亏与预测展示
- **K 线**：30m/60m/1D、缩放/平移/区间切换、区域过滤（逐指标）、forecast corridor、成本线
- **Forecast**：1/3/5/10(/20) 各 horizon 的 PIT、无泄漏、walk-forward、校准、provenance
- **安全**：注册 fail-closed、CSRF、会话撤销、无凭据入库入文档

## 十一、最终验收清单（第一版完整落地定义）

- [ ] 导航按用户任务组织；14:30 是模式；K 线是详情；旧四页面入口消失
- [ ] 用户可添加 ETF → 关注 → 持仓 → 看盈亏/预测/K 线全链路
- [ ] 板块发现 → ETF → 持仓链路完整，proxy 语义标注
- [ ] 唯一 MA/MACD/KDJ/RSI/TD9；支撑压力统一且区域化
- [ ] 图表 zoom/pan/crosshair/成本线/区域/indicator filter/corridor
- [ ] 1/3/5/10(/20) 全列展示，20 日过验证门槛
- [ ] 新闻分层展示 + provenance；OCR 可选启用路径文档化
- [ ] 14:30 必达；scheduler 失败隔离；备份/健康检查/HTTPS 不回退
- [ ] 100+ ETF 性能门槛（P95 < 300ms 快照读）
- [ ] 全程无假数据 fallback、无凭据泄露、无自动交易

---

## 十二、明确不做

1. 不创建第五、第六个平行决策页面；
2. 不在任何页面/JS 复制指标或评分公式；
3. 不把 TD9 数字直接换算成价格；不把 `chan_zone_approx` 宣传成完整缠论；
4. 不复活旧 20 日 fallback；不让新闻/单次回测翻转 canonical action 或自动改参；
5. API 失败不显示任何历史静态行情；OCR 永不跳过人工确认；
6. 图表第三方库若采用，必须 dist 锁版本进 `static/`（CSP `script-src 'self'`），禁 CDN；
7. 不因 UI 重构破坏生产调度/认证/备份；不自动 push/merge；凭据永不入代码/文档/聊天。

---

## 十三、统一问题追踪清单（合并五份材料，去重后）

| ID | 问题 | 批次 | 状态 |
|---|---|---|---|
| 1 | 生产凭据明文泄露 | PR-A | 待处置 |
| 2 | 注册默认不设防（邀请码默认值） | PR-A | 待处置 |
| 3 | kline 静态假数据兜底 | PR-A | 待处置 |
| 4 | 指标三处计算口径不一 | PR-B | 待处置 |
| 5 | 支撑/压力输入不一（160根/amount=0 vs 全量） | PR-B | 待处置 |
| 6 | 前端二次打分与服务端分并存 | PR-B | 待处置 |
| 7 | kline 死代码 Bearer（fundDecisionToken） | PR-A | 待处置 |
| 8 | 「锁定/退出」等跨页文案不一 | PR-A | 待处置 |
| 9 | 页面命名混乱（一页三名） | PR-C | 待处置 |
| 10 | 四页面按历史拆分（IA 收敛） | PR-C | 改造中 |
| 11 | 缺统一 Presenter（跨页漂移根因） | PR-B | 待建设 |
| 12 | 支撑压力未区域化 | PR-F | 待开发 |
| 13 | 图表无缩放/平移/十字线 | PR-F | 待开发 |
| 14 | TD9 无价格支撑压力 | PR-F | 待开发 |
| 15 | 无 30m/60m 分钟线体系 | PR-G | 待开发 |
| 16 | 无 20 日预测 | PR-H | 待验证后开发 |
| 17 | 预测下拉不利于横向比较 | PR-C | 待开发 |
| 18 | 持仓页无预测列/当前动作 | PR-D | 待开发 |
| 19 | 用户无法自助添加 ETF | PR-D | 待开发 |
| 20 | 行业板块非一等页 | PR-E | 待开发 |
| 21 | 新闻 UI 未以 model_analysis 为首要解释 | PR-I | 待开发 |
| 22 | 1430 每请求全量重算 | PR-B | 待优化 |
| 23 | `_latest_forecasts` 全量拉取 | PR-B | 待优化 |
| 24 | CurrentDecisionService 全表扫 | PR-B | 待优化 |
| 25 | 调度槽位过密且两处定义 | PR-B 核对→PR-F 收敛 | 待处置 |
| 26 | 刷新机制三页三样 | PR-B(SSE)→PR-F | 待统一 |
| 27 | OCR 生产关闭（预期内） | 保持 | 文档化 |
| 28 | forecast_version 列扩容 | 已完成 | 复核迁移入库 |
| 29 | scheduler 收盘链补齐 | 已完成 | 补回归测试 |
| 30 | AKShare 新闻缺失 | 已完成 | — |
| 31 | reports 目录权限 | 已完成 | 写入部署文档 |
| 32 | bind mount 生产治理策略 | 待决策 | PR-A 期间定 |
| 33 | 一次性邀请码 | 可选增强 | Backlog |
| 34 | 100+/300 标的压测 | PR-I 前 | 待执行 |
