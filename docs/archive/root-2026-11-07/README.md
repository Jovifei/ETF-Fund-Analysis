# 归档索引 — 2026-11-07 项目瘦身

2026-11-07 按所有者指示对全仓文档瘦身：与现行技术方向冲突或已被后续决策取代的文档不再留在现行层。
本目录（root-2026-11-07）收纳原 docs/ 根目录的 67 篇 + 仓库根 VALIDATION.md，共 68 篇：
版本专题（_V0xx/_V1xx）、验收/测试报告、部署收据、旧路线图与计划、旧交接与审计汇总。
同批归档的还有：

- `docs/archive/planning-2026-11-07/` — 原 docs/planning/（11 篇）与 docs/plans/（1 篇）；
- `docs/archive/superpowers-2026-08/` — 2026-08 的设计稿与计划（4 篇）。

同期处理：4 篇仍现行的契约（CURRENT_DECISION_SOURCE_CONTRACT、SCHEDULER_RESILIENCE、
SINGLE_DECISION_SURFACE_AND_FORECAST_SEMANTICS、REFERENCE_BOARD_PARITY）移入 `docs/contracts/`；
1 篇过期分支说明 CALC_DECISION_BRANCH.md 已删除（内容早已并入 main）。
归档文件只读、仅作历史沿革；任何结论以现行层（根目录 STATUS.md / HANDOFF.md、docs/ 根目录保留文档、
docs/contracts/）为准。全部移动均经 git mv，可由 git 历史完整追溯。执行记录见
`docs/handoffs/CONSOLIDATION_20261107.md` §12。
