# 文档梳理过程记录 — 2026-09-06

## 目的

用户要求重新理解整个项目的最终目标、每一步实现要求、页面/组件/颜色参考、开源借鉴、历史卡点和剩余工作，并整理 `docs/`，方便后续 AI 接手。

本记录保留本轮梳理过程本身，避免下一位 Agent 不知道“这些结论是怎么来的”。

---

## 1. 输入来源

### 1.1 用户提供的共享聊天链接

用户提供：

```text
https://chatgpt.com/share/6a9cd43a-0a04-83e8-b5f8-c0ba299ff3f1
```

本轮 Web 抓取结果：`cache miss`，搜索引擎也未索引该 share id；运行容器没有可用的外网 DNS 作为替代抓取手段。

因此本轮没有把无法读取的共享页内容伪装成已读取事实。

### 1.2 当前项目会话上下文

可确认用户持续强调：

- 每天约 14:30 对 ETF 做买/卖/观望研究；
- 使用 MACD/KDJ/成交量/新闻等；
- 预测明日及 3/5/10 日；
- 到压力位/支撑位辅助卖出/买入判断；
- 点击 ETF 应有 K 线详情；
- 系统长期运行在自己的服务器；
- 页面/入口不要因历史迭代越堆越乱。

### 1.3 GitHub main 提交历史

重点审查 2026-09-03 到 2026-09-05 的主线提交，包括：

- canonical current decision；
- 1/3/5/10 horizon 对齐；
- purged walk-forward；
- point-in-time factor diagnostics；
- P0 数据真实性/安全修复；
- Indicator/SR single source；
- 全局 `/etf/{code}`；
- watchlist/持仓预测融合；
- `/boards`；
- S/R Zone + TD9 + Canvas 交互；
- MarketBar 30m/60m；
- v0.8.0 release；
- v0.8.1 task-driven navigation。

### 1.4 重点文档

交叉审查：

- `AGENTS.md`
- `STATUS.md`
- `HANDOFF.md`
- `docs/GITHUB_RESEARCH.md`
- `docs/DECISION_BOARD_WORKBUDDY_REPLICA.md`
- `docs/COMPREHENSIVE_SYSTEM_REFACTOR_PLAN.md`
- `docs/HORIZON_ALIGNMENT_20260903.md`
- `docs/ETF_DATA_ONBOARDING_PLAN.md`
- `docs/ETF_1430_DECISION_WORKBENCH.md`
- `docs/ETF_1430_VALIDATION.md`
- `docs/ARCHITECTURE.md`
- `docs/IMPLEMENTATION_MATRIX.md`
- `docs/RELEASE_V080.md`
- `docs/NAVIGATION_CONTRACT_V081.md`

---

## 2. 本轮最重要的裁决

### 裁决 A：原始目标不是“做更多页面”
最终目标被定义为**14:30 个人 ETF 决策闭环**。板块、持仓、研究、K 线、新闻和预测都是为这个闭环服务。

### 裁决 B：当前代码/测试高于旧 Master Plan
Master Plan 非常重要，但它是方案蓝图，不是所有细节的当前事实。以下实际实现不同于计划：

- `/portfolio` → 当前 `/holdings`；
- `/workbench/1430` → 当前 `/decision/1430`；
- 20D → 当前正式 horizon 仍为 1/3/5/10；
- Lightweight Charts → 当前为自绘 Canvas；
- “14:30 完全首页内嵌” → 当前先做到语义二级模式，仍有独立 HTML。

这些差异必须被记录为“经过实现过程后的新合同”，不能让后续 Agent 机械回滚。

### 裁决 C：WorkBuddy 是视觉/信息架构参考，不是源码复制目标
历史文档明确说明当时也无法自动读取 WorkBuddy 动态页。因此当前可以遵守：信息密度、颜色语义、指标解释、分组方式；不能要求未知的像素级 CSS 一致。

### 裁决 D：真正未完成的是验证，不是功能数量
最核心的剩余阻塞是：

- 真实 14:30 point-in-time 分钟历史；
- 费用/滑点/可成交性；
- 样本外 walk-forward；
- forecast 校准；
- shadow run；
- 人工批准。

UI legacy 壳拆分属于体验/维护债，但优先级低于决策有效性证据。

---

## 3. 新增的当前权威文档

### `docs/README.md`
新增 docs 权威索引与冲突裁决顺序。

### `docs/PROJECT_HANDOFF_20260906.md`
新增完整项目交接：目标、历史阶段、实现规则、开源借鉴、视觉依据、卡点、未完成项。

### `docs/UI_UX_CONTRACT.md`
新增当前页面、路由、组件、颜色与设计参考合同。

### `docs/ROADMAP_TO_FINAL.md`
新增只包含剩余工作的路线图，优先真实 14:30 验证与预测校准。

### `docs/DOCS_RECONCILIATION_20260906.md`
即本文，记录文档梳理过程和证据边界。

---

## 4. 对旧文档的处理原则

本轮不批量删除旧文档。原因：

- 分支/发布/修复历史有审计价值；
- 某些“后来未采用”的建议仍解释了为什么做当前选择；
- 删除会让后续无法区分“没想到”与“考虑后放弃”。

处理方式：

1. 用 `docs/README.md` 建立权威层；
2. 更新最容易误导 Agent 的当前架构/矩阵/14:30 文档；
3. 对 Master Plan / WorkBuddy 实验保留历史原文，但在索引和交接中明确其当前状态；
4. 根 `STATUS.md` / `HANDOFF.md` 应更新为新的接手入口，避免 `AGENTS.md` 要求 Agent 先读到过期 0.7 信息。

---

## 5. 仍需人工补充的内容

若后续能从 ChatGPT UI 打开共享聊天，建议人工导出或粘贴以下内容后再补本文：

- 最早用户对页面视觉的原话/截图；
- WorkBuddy/其他 AI 给出的具体 UI 组件建议；
- 用户曾明确否决的页面布局；
- 若有尚未进入 Git/docs 的业务规则。

补充时必须标注“来自聊天原始需求”，并与当前 main 进行差异核对。不能因为聊天中曾提过某项功能，就绕过现在的安全/验证合同直接实现。

---

## 6. 本轮文档变更的验收方式

文档提交前检查：

- 所有当前路由与 `NAVIGATION_CONTRACT_V081.md` 一致；
- 应用版本写为 0.8.0，不把导航合同 v0.8.1 错写成 package version；
- forecast 当前 horizon 写为 1/3/5/10；
- 20D 被标为可选未来研究；
- Canvas/Lightweight Charts 的“计划 vs 实际”不混淆；
- 14:30 未被描述为已完成真实历史验证；
- 没有写入密码、Token、Cookie、账户或生产 secret。

本轮是文档重构，不修改策略/指标/预测/数据库语义。
