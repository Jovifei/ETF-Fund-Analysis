# 文档入口：当前实现与下一阶段目标分开读

更新：2026-09-06，用户补充Kairo截图、本地研究工作站与开源吸收要求后。
应用基线0.8.0；现有导航合同v0.8.1；**vNext为规划，尚未部署**。

## 首次接手

先读根目录 `AGENTS.md`、`STATUS.md`、`HANDOFF.md`，然后按下表阅读。

| 文档 | 用途 | 状态 |
|---|---|---|
| [ETF_WORKSPACE_VNEXT](planning/ETF_WORKSPACE_VNEXT.md) | 最新目标、需求ID、步骤、依赖、验收、ETF/个股分期 | 当前目标总案 |
| [OSS_ABSORPTION_20260906](research/OSS_ABSORPTION_20260906.md) | 指定项目/补充Skill的源码锚点、可吸收项、许可与缺口 | 定向审阅，未安装 |
| [UI_UX_CONTRACT](UI_UX_CONTRACT.md) | Kairo式左栏/搜索/账户、页面、组件、配色、空态 | 待实施 |
| [LOCAL_RESEARCH_BRIDGE](planning/LOCAL_RESEARCH_BRIDGE.md) | 本地Codex/Vibe产物、API模式、权限、上传/审核/发布 | 待实施 |
| [FACTOR_SKILL_GOVERNANCE](planning/FACTOR_SKILL_GOVERNANCE.md) | 持仓三类含义、因子相关性、风格Skill、研究准入 | 待实施 |
| [PROCESS_LOG_20260906_VNEXT](PROCESS_LOG_20260906_VNEXT.md) | 这轮做过/没做过什么、覆盖范围、决策修订与交接 | 过程记录 |

## 现有代码合同与历史

`NAVIGATION_CONTRACT_V081.md`、`CURRENT_DECISION_SOURCE_CONTRACT_20260903.md`、`HORIZON_ALIGNMENT_20260903.md`、`ARCHITECTURE.md`和`IMPLEMENTATION_MATRIX.md`描述既有基线，不能当新功能已完成的证明。`ETF_1430_VALIDATION.md`保留策略资格门禁；不阻止先交付诚实标注的研究页面。

`RELEASE_V080.md`是历史发布证据，不证明今天ECS版本/数据仍一致。`GITHUB_RESEARCH.md`是早期调研，本轮补充项目看新审阅。`COMPREHENSIVE_SYSTEM_REFACTOR_PLAN.md`、WorkBuddy实验、旧交付prompt和日期型记录保留审计价值。

[上一轮项目总交接原文](https://github.com/Jovifei/ETF-Fund-Analysis/blob/3c7bdc7ff36b3dea482651e087127a33c4974903/docs/PROJECT_HANDOFF_20260906.md)及[旧路线图](https://github.com/Jovifei/ETF-Fund-Analysis/blob/3c7bdc7ff36b3dea482651e087127a33c4974903/docs/ROADMAP_TO_FINAL.md)按固定提交保存。没有删除历史来掩盖需求变更。

## 冲突处理

安全与数据真实性继续遵守AGENTS。**产品目标以用户最新明确需求为准；实现状态以固定版本代码、测试和实际部署证据为准。** 两者冲突应记录为待实现差距，不能用代码现状否决需求，也不能用规划冒充完成。技术选型和新增工具权限需要独立评审。

本轮只学习/规划/整理文档。后续AI未获实施授权，不安装项目、不启动任务、不修改业务代码、不自动交易。任何状态升级写清证据日期、版本、范围和未覆盖项。
