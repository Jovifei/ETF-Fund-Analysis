# v1.0.4 验证记录

本轮从 main 57470eabcad35a6038574e893e7245f0d1adb387 接续。只在 feat/v104-market-workspace-20260909 分支开发，不合并main，不部署生产，不读取用户私有数据。

## 已完成的分阶段代码验证

- 55c95b8c：板块关联检索、目录多源后备及发现任务状态。独立云端应用前专项测试通过。
- 8e1bd483：日/周/月K线、研究辅助线、原表排序、小星标、共享1/5/20日研究。独立专项、TS、Vue及构建通过。
- 777bded1：AES-GCM模型配置、外部主密钥、明确计费确认、用户/额度/租约检查、新闻反馈与普通/Plus管理。独立专项、TypeScript、单测、build通过。
- 3029ddb6：研究任务有界静默刷新，不因刷新重建输入表单；新增2项Vue回归，26项单测通过；会员浏览器测试不再依赖其他文件的成员初始化。

原版 WorkBuddy 的表头合同保留，但用户要求移除重复“较昨日”列，旧静态断言改验其移除与涨幅排序存在。小目录回退测试按当前实际部分覆盖状态断言，不再把1个ETF当作完整目录；未删除测试或放宽数据/认证门禁。

## 完整验收

此文档提交启动最终 ci/workspace-ci；未取得完成结果前不得据本文件声称全部通过。最终固定代码SHA与运行编号、测试计数、跳过原因会追加到验收收据和PR。

完整门禁包括后端全量、SQLite迁移、旧JS、源码安全扫描、ShellCheck、Compose、生产Docker镜像/容器smoke；工作站门禁包括v104专项、依赖审计、TS、Vue、build、真实HTTP Chromium一般及认证旅程。

## 与现场验证分开

云端浏览器使用隔离Mock与测试账户，模型网络在单元测试使用受控注入，真实Key不进入CI。未取得本人数据商权限/实际新闻源、真实API付费响应、Windows DPAPI/PaddleOCR现场、本人Codex/Vibe登录、E盘/阿里云磁盘统计与生产部署证据。按LOCAL_ACCEPTANCE_V104.md逐项现场完成。未上线任何支付系统、自动云地数据同步、完整缠论引擎、自动学习改生产权重；20日仅未校准实验。不得用“已配置”、HTTP202或容器Up代替端到端数据成功。

## 2026-09-10 接收复核结果

- 固定接收 `910e77fc866f123e0d18103048243513e3edb666`；PR #32 的 `workspace-ci` 成功，完整 `ci` 在旧 WorkBuddy JS 合同断言处失败，公开数据观察成功。
- 本地审核提交 `b8112d4` 将重复“较昨日”列断言更新为 v1.0.4 合同，并修复新闻 publication/fetched 时区语义。修复后全量 pytest exit 0（5 个条件跳过）、前端 27/27、普通 Playwright 15/15、认证 Playwright 2/2、compileall/旧 JS/密钥扫描/diff check/SQLite migration 通过。
- 本地持久副本使用真实 `akshare`、Mock fallback 关闭，目录/板块/两只 ETF/有限批次/新闻任务和重启证明均有独立收据；Docker daemon 未运行，专用 PostgreSQL、镜像 build 和 container smoke 未通过且未宣称通过。
- 新闻状态现场结果：200 条 `akshare:eastmoney`，最新 publication 带 `+08:00`，fetched 按 `+00:00`，前端筛选与显示共用 parser；无效/未来时间显示待核实。
- 当前仍未完成实时中证全指近期数据、量价因子资格、真实 OCR、Vibe/Codex 真人任务、Windows DPAPI、14:30 PIT、分钟线和最终研究资格。生产、main 合并和标签保持不动。
