# 当前状态：v1.0.5 审核修复分支（2026-09-13）

这是代码和隔离验证状态，不是生产部署收据。PR #33：`fix/v105-audit-blockers-20260912` → `codex/v105-handoff-local-20260910`；基线 `6d09ddb6cfde39d9d8e6a30783f9bdee838bc379`。没有合并 main、移动标签、修改用户账户或生产数据库。

## 必须纠正的旧结论

旧文档的“新浪 v102 量额恢复即资格通过”不再成立。均价比值不能认证绝对单位；历史价格断点未完成独立行情与公司行动对账。588200 已找到 1:3 拆分公告，但未因此更改原记录、成本、收益或研究资格。代码启用更严格门禁后，部分标的可能显示更多明确缺口，不允许为减少异常数量而放宽门禁。

## 当前代码

应用/前端版本统一 1.0.5；数据契约 cn-fund-shares-cny-v1.0.3-audit，特征 feature-store-v0.7.3-input-mask，指标 ind-v0.7.3-audit，预测 similarity-corridor-v0.7.3-audit，策略 signal-v0.7.2-qualification-audit。迁移 head 保持 d40609090002。旧快照不能只改版本字段冒充重算。

累计修复覆盖新浪资格冻结、价格断点拒绝、量额缺失 mask、全输入哈希、同版本前值、统一结算目标、partial/failed 传播、衍生任务恢复、指数盘后任务、跨进程流水线锁、14:30交易日/未来报价门禁、子进程独立登录、NTFS ACL、无效产物终态、不重复付费以及发布 manifest。

新增只读诊断 scripts/audit_research_inputs.py；新回归覆盖 Windows 中文编码和原版表慢脚本丢筛选。原 WorkBuddy 模板、统一总览和详情均保留。主流水线、工作站浏览器和 Windows/PostgreSQL 必须在同一个最终 SHA 核实；中间失败及其后跳过项不计通过。

## 仍未获得的资格

真实新浪绝对单位认证、完整公司行动/复权总收益序列、真实14:30历史回测与前瞻观察、本人Codex登录/付费响应/端到端公网回传没有因为CI通过而自动完成。14:30最终 actionable 保持 false。只读审核工具退出0只表示成功产出报告，不表示数据合格。

[逐项关闭矩阵](docs/audits/CLOSURE_20260913.md) · [版本记录](docs/versions/V1.0.5.md) · [交接](HANDOFF.md)。最后测试收据与固定应用SHA由 docs/audits 下的最终验收文件补充。

[原状态完整归档](docs/archive/pre-audit-close-20260913/STATUS.md)。旧生产收据保留当时证据，但本轮未访问服务器，不能作为今天的现场状态。
