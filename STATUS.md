# 当前状态：v1.0.5 企业行为研究修复已部署，资格门禁继续加固（2026-09-20）

企业行为研究修复基线是 `172db210e3e7e4daa252bdd2746466f79e5da595`。该版本已把四只 ETF 的官方份额拆分只应用于内存研究序列，保留原始展示日线，并修复 stale 重算、信号恢复和任务状态传播。生产 API、worker、scheduler 已切换到该源码并通过公网健康与页面检查；生产镜像标签仍是旧基础镜像，当前代码由固定源码目录绑定挂载，不能把镜像标签描述成新构建。接手时以 `git rev-parse HEAD` 与 `origin/main` 的完整 SHA 为准。

绝对量额独立认证合同、公司行动展示/研究序列分离、14:30 PIT/OOS 闸门、实时时间戳 operational-grade 检查和 Codex `live_ready=false` 均已进入主线。这些是失败关闭门禁，**不是**生产数据合格证明。

## 必须纠正的旧结论

旧文档的“新浪 v102 量额恢复即资格通过”不成立。均价比值不能认证绝对单位。512000、512480、515880、588200 的价格断点已与官方份额拆分对账，但公告只支持研究序列连续化，不认证原始成交量、成交额或完整总收益。

## 当前代码

应用/前端版本统一 1.0.5；数据契约 cn-fund-shares-cny-v1.0.4-corporate-action-research，特征 feature-store-v0.7.3-input-mask，指标 ind-v0.7.3-audit，预测 similarity-corridor-v0.7.3-audit，策略 signal-v0.7.2-qualification-audit。迁移 head 保持 d40609090002。官方拆分事件只生成独立内存研究序列，原始展示日线不改；旧快照不能只改版本字段冒充重算。

累计修复覆盖新浪资格冻结、价格断点拒绝、量额缺失 mask、全输入哈希、同版本前值、统一结算目标、partial/failed 传播、衍生任务恢复、指数盘后任务、跨进程流水线锁、14:30交易日/未来报价门禁、子进程独立登录、NTFS ACL、无效产物终态、不重复付费以及发布 manifest。

只读诊断 `scripts/audit_research_inputs.py` 保留。FTShare 资格脚本已改为失败关闭：接口有记录不再等于 qualified，必须同时具有独立绝对单位证据和 operational-grade 时间证据。2026-09-20 对五只 ETF 的 bounded probe 全部返回 CapabilityUnavailable，因此 FTShare 仍不得进入生产回退链。

## 仍未获得的资格

35 只标的的独立绝对单位认证、完整公司行动/复权总收益序列、真实 14:30 历史回测与前瞻观察、本人 Codex 登录/付费响应/端到端公网回传仍未完成。生产研究板可以展示 stale 研究结果，但 `actionable` 保持 false。下一主线任务是在可用的第二行情源恢复后完成同日量额对账；在此之前不启动预测校准。

[逐项关闭矩阵](docs/audits/CLOSURE_20260913.md) · [版本记录](docs/versions/V1.0.5.md) · [交接](HANDOFF.md)。最后测试收据与固定应用SHA由 docs/audits 下的最终验收文件补充。

[FTShare 现场资格收据](docs/audits/FTSHARE_QUALIFICATION_20260920.md) · [原状态完整归档](docs/archive/pre-audit-close-20260913/STATUS.md)。
