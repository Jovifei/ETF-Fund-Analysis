# 当前工程交接

目标仍是14:30可追溯ETF/LOF研究工作台；总范围以[总路线](docs/PROJECT_MASTER_ROADMAP.md)为准。当前仅完成两批有界图表显示修复及发布文档精简，不代表S4或全项目验收完成。

## 代码与验证身份

- 仓库：`Jovifei/ETF-Fund-Analysis`；原分支：`codex/post-release-indicator-audit-20261004`。
- 本批提交前远端基线：`8c7f34209726862451b6a5379669b35cf134c593`，tree `6f604eb9fe3ef1ece3fe6cf71d1550034c10dcc6`。
- 两批实现分别统一方向显示，以及阻止原始蜡烛上的错口径研究趋势线。公式、原数值、资格、数据库及迁移未变；必要前端依赖安全更新单列验收。
- 196项前端、1762项后端/11跳过、独立138项/30投影边界、类型/构建均为已保存的源码验证。脱敏仅重核文件哈希与文档生成，不声称重新执行过这些测试。
- 新提交身份以原分支实际SHA/tree为准。精简改变文档tree；实现/测试字节仍由两份审计中的SHA-256绑定。不能把相同tree的本地基线提交当成远端父提交。

## 下一步与边界

1. 从真实远端父提交非强制发布两批完整修复，检查最终tree与候选完全一致。
2. 核该SHA的ci、workspace-ci、audit-platforms，不继承旧提交成功。趋势修复的新浏览器/截图验收仍待完成。
3. 部署前核当前运行版本与可回退状态；部署、正常私有验收/R10、实体手机结果分别记录。此交接不宣称当前生产已更新。
4. S8-F0真实权限/许可、5m/15m量额单位、源时间、PIT/OOS及可行性仍为关键路径。UNKNOWN/actionable=false/not_calibrated保持，不自动激活运行时或交易。

进度JSON为唯一可编辑台账；保留S0–S9全部任务与原五维验收状态。修改后运行 `python scripts/update_project_progress.py` 及 `--check` 生成MD/HTML，不手改生成视图。

[当前状态](STATUS.md) · [当前任务](tasks/todo.md) · [方向显示审计](docs/audits/S4_U08_SR_DIRECTION_DISPLAY_20261005.md) · [趋势口径审计](docs/audits/S4_U09_TREND_PRICE_BASIS_20261005.md)

## 必要前端安全更新

发布前完整审计发现高危/严重依赖项，已在隔离副本验证Vue3.5.42、Vitest4.1.11及source-map-js1.2.2的必要闭包。新环境23文件196项前端、类型/构建通过；audit为0高危/严重/中危、余1低危。原业务与测试源码保持，后端既有1762/11结果按相同字节复用，不冒作重跑。

本地浏览器因socket权限在页面/断言前退出；精确CI的smoke、认证、响应式及截图仍待完成。无Vitest5、强制override或门禁放宽。见[安全兼容证据](docs/audits/FRONTEND_SECURITY_COMPATIBILITY_20261006.md)。
