# 文档入口与权威层级

更新时间：2026-09-06  
当前应用发行版本：`0.8.0`  
当前导航合同：`v0.8.1`（这是产品/路由合同版本，不代表 `pyproject.toml` 已升级到 0.8.1）

本目录历史文档很多，部分记录的是当时的实验、分支状态或规划。后续 Agent **不要按文件日期猜权威性**，按下面顺序阅读。

## 1. 接手必读：当前权威文档

1. [`PROJECT_HANDOFF_20260906.md`](PROJECT_HANDOFF_20260906.md)  
   项目最终目标、来龙去脉、阶段实现方式、开源借鉴、当前卡点和剩余目标。
2. [`UI_UX_CONTRACT.md`](UI_UX_CONTRACT.md)  
   页面结构、路由、组件、颜色、交互、视觉参考与禁止事项。
3. [`ROADMAP_TO_FINAL.md`](ROADMAP_TO_FINAL.md)  
   从当前 main 到“真正完成”的剩余工作、优先级、验收标准。
4. [`NAVIGATION_CONTRACT_V081.md`](NAVIGATION_CONTRACT_V081.md)  
   当前 URL 与导航语义的精确合同。
5. [`ARCHITECTURE.md`](ARCHITECTURE.md)  
   当前运行架构、单一计算权威、数据/预测/14:30 边界。
6. [`IMPLEMENTATION_MATRIX.md`](IMPLEMENTATION_MATRIX.md)  
   能力完成度、已验证证据与尚未取得的资格。
7. [`DOCS_RECONCILIATION_20260906.md`](DOCS_RECONCILIATION_20260906.md)  
   本轮文档梳理采用了哪些证据、改了什么、哪些内容因共享聊天链接不可抓取而无法直接核对。

代码修改前仍必须先读仓库根目录：`AGENTS.md`、`STATUS.md`、`HANDOFF.md`。

## 2. 当前专题合同

- [`CURRENT_DECISION_SOURCE_CONTRACT_20260903.md`](CURRENT_DECISION_SOURCE_CONTRACT_20260903.md)：当前动作唯一来源。
- [`HORIZON_ALIGNMENT_20260903.md`](HORIZON_ALIGNMENT_20260903.md)：当前预测期限固定为 `1/3/5/10`；20D 仅保留历史兼容/未来研究资格。
- [`ETF_1430_DECISION_WORKBENCH.md`](ETF_1430_DECISION_WORKBENCH.md)：14:30 决策模式的当前语义和数据边界。
- [`ETF_1430_VALIDATION.md`](ETF_1430_VALIDATION.md)：真正验证 14:30 策略所缺的 point-in-time 证据。
- [`FORECAST_CORRIDOR.md`](FORECAST_CORRIDOR.md)：预测走廊语义。
- [`ETF_DATA_ONBOARDING_PLAN.md`](ETF_DATA_ONBOARDING_PLAN.md)：免费/增强数据源的实测历史与能力矩阵。
- [`ALIYUN_DEPLOYMENT.md`](ALIYUN_DEPLOYMENT.md)：生产部署与回滚。
- [`GITHUB_RESEARCH.md`](GITHUB_RESEARCH.md)：开源项目调研及“借鉴而不耦合”的边界。

## 3. 发布记录

- [`RELEASE_V080.md`](RELEASE_V080.md)：v0.8.0 架构收敛发布记录。
- [`NAVIGATION_CONTRACT_V081.md`](NAVIGATION_CONTRACT_V081.md)：v0.8.0 发布后的任务驱动导航收敛合同。

## 4. 历史设计依据：保留，但不能直接当当前实现合同

### `COMPREHENSIVE_SYSTEM_REFACTOR_PLAN.md`
三份 AI 方案综合形成的 Master Plan。它解释了为什么要收敛为“决策/板块/持仓/研究 + ETF 详情 + 14:30 模式”，非常重要；但有几项后来没有原样实现：

- 规划建议引入 TradingView Lightweight Charts；当前实际实现仍是 CSP-safe 原生 Canvas，并已具备缩放/平移/十字光标。
- 规划曾提出 `/portfolio`；当前合同使用 `/holdings`。
- 规划把 20D 作为后续目标；当前经过专门对齐后仍以 `1/3/5/10` 为正式研究期限。
- 规划要求 14:30 完全内嵌首页；当前先收敛为 `/decision/1430` 的“决策二级模式”，仍复用独立 HTML。

因此：**用它理解目标和取舍，不要用它覆盖当前路由、预测期限或实现事实。**

### `DECISION_BOARD_WORKBUDDY_REPLICA.md`
WorkBuddy 风格视觉实验记录。应继续保留作为 UI 设计来源，但其中“前端研究评分”已经被后续“服务端为唯一计算权威”原则替代。当前应以 `UI_UX_CONTRACT.md` 为准。

### 其他日期型/分支型文档
如 branch reconciliation、局部修复计划、旧交付 prompt 等，主要用于追溯当时为什么做某个决定。除非当前权威文档明确引用，否则不应恢复旧路由、旧评分或旧数据回退。

## 5. 文档冲突时的裁决顺序

发生冲突时按以下顺序裁决：

1. `AGENTS.md` 的安全/真实性/策略边界；
2. 当前 `main` 的代码和自动化测试；
3. 本页“当前权威文档”；
4. 最新发布/导航合同；
5. 历史计划、实验和聊天摘要。

尤其禁止因为旧规划写过某项能力，就把“计划中”描述成“已实现/已验证”。
