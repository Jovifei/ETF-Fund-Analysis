# 当前工程交接

2026-10-27。目标：本机定时采集和确定性研究→有界展示包→网站更新；同批AI解释和邮件需独立投递证据。数据/持仓/配置及回滚资产受保护，不自动交易。

## 当前执行

- 分支`codex/daily-pipeline-repair-20261026`，基线main `7b3a575`；v1.0.13候选尚未发布。主目录Owner未提交文件保留，实际生产仍v1.0.12 / producer `dcffa8e`。
- 计划`tasks/plans/2026-10-26-daily-pipeline-repair.md`；10-26事实与JSON证据在`docs/audits/DAILY_PIPELINE_GAP_20261026.md`及同目录EVIDENCE文件。
- 已实现P0诊断、P1日线研究依据与下游输入隔离、P2投影复用及base分组。合法qfq/hfq、非目标背景历史时点、旧闭市证明/旧包兼容均补回归。
- P3 SMTP代码默认停用；Jovi明确稍后配置，继续网站修复。不得启用实际发送或将44项合成测试称作收件验收。
- 当前聚焦测试、审查与真实只读投影对照仅为候选证据；最终SHA、完整测试/CI/网页审核、发布和自然任务尚未收据闭环。

## 接续顺序

1. 完成剩余审查及缺陷闭环，冻结新SHA/tree与报告；运行全量、静态、前端、精确CI。
2. 同一“基金决策”项目普通网页GPT复审固定GitHub提交；不创建Cloud Work，不把连接或计划通过视为代码通过。
3. 备份验证后，在隔离store预验新生产者；本地任务、源码/策略身份、登记与云端接收成套切换，保留旧组合可回滚。读取过期包仍标历史；不得重封旧内容冒充新数据。
4. 核新日线/派生/包/回执与总览、详情、图表同generation；正常用户登录、手机与两个真实交易日、7–14日观察分别记账。新SMTP配置/启用/收件另验。

保留UNKNOWN/actionable=false/not_calibrated。不得reset/clean/stash、强推、直写生产数据库或清理受保护资产；所有辅助后台进程必须隐藏启动。

## 浏览器认证部署契约

生产保持`AUTH_ENABLED=true`、持久`DATABASE_URL`、`AUTO_CREATE_SCHEMA=false`、HTTPS `AUTH_COOKIE_SECURE=true`；首次管理员由`auth-bootstrap-admin`初始化。已有用户与持仓保留，不把展示库当账户库，不回显凭据。
