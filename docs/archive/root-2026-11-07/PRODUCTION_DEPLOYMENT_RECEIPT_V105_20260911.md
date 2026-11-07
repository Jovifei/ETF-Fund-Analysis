# v1.0.5 接收分支公网部署收据（2026-09-11）

## 授权与保护

Jovi 在本轮明确要求继续修复并部署到公网生产。部署使用独立接收分支和新源目录，没有覆盖原工程脏改动，没有重置、清空或初始化生产 PostgreSQL、账户、持仓和自选数据。

- 接收分支：`codex/v105-handoff-local-20260910`
- 首次切换代码 HEAD：`409a5e5b28cba190736ca930eba80702f74b4317`
- 当前量能修复代码 HEAD：`208858e2e05b8ba6b31f7a4b85a9531044cc3e50`
- 固定基线：`46c713d4a7f6f247461ec9b075948f25c6741df7`
- 当前服务器归档：`/opt/china-fund-decision/deploy-v105-208858e`
- 当前归档 SHA-256：`a311c3cadea839013eaefdac03668eee0f84daee9be47ecb0f573169ea3640a1`
- 运行镜像：既有 `etf-workspace:v1.0.4-runtime-20260910`；本轮没有在服务器直接 build。

## 备份与回滚

切换前通过现有备份脚本生成：

- `/opt/china-fund-decision/backups/fund_decision_20260911_084351.sql.gz`
- SHA-256：`cd2e8088d8c058778399763ec1bc68e060cfb480aa1eb08a74c6f27464a58d8c`
- 权限：`600`，大小 `17,597,701` bytes

旧 v1.0.4 运行目录 `deploy-v104-3e4b9fa-r2`、旧 Compose、旧镜像和精确回滚文件 `compose.production.v104-3e4b9fa-r2.rollback.yml` 均保留。新 Compose 使用独立项目名和容器名，失败路径为停止 v105、启动该回滚 Compose。

## 首次 v105 切换证据（08:52）

1. 远端 `docker compose config -q` 通过。
2. 诊断 Compose 在 `127.0.0.1:18081` 以 v105 源挂载启动；Alembic 使用 PostgreSQL 连接并无待迁移，API health 返回 production、`public_composite`、认证开启；诊断容器已清理。
3. 正式切换先停止 v1.0.4 三容器，再启动 `etf-workspace-v105-production-api/worker/scheduler`。
4. 切换后 API、worker healthy，scheduler 运行；内部和公网 `https://etf.joviluma.com/api/health` 均返回 `status=ok`、`version=1.0.4`、`environment=production`、`provider=public_composite`、`auth_enabled=true`。
5. 公网根页面 HTTP 200（568 bytes）；未登录访问受保护的 `/api/workspace/data-health` 返回 401，认证门禁仍在。

生产环境显式保持 `ALLOW_MOCK_FALLBACK=false`、`AUTH_ENABLED=true`、`SCHEDULER_ENABLED=true`、`BALANCED_REFRESH_ENABLED=false`、`WORKSPACE_DISCOVERY_ENABLED=false`、模型/OCR/Bridge/每日复盘关闭。应用版本字段仍为仓库实际的 `1.0.4`，没有把接收批次名称伪装成不存在的应用版本。

## 首次切换时数据与持久性复核

切换后只读查询生产 PostgreSQL：`auth_users=3`、`holdings=0`、`user_watchlist_entries=6`，数据库约 52 MB，未出现账户或个人数据重置。

切换时服务器本地时间为 `2026-09-11T08:52:20+08:00`，尚未进入 A 股盘中报价窗口；已有两只 ETF 数据保持：

- `510300.SH`、`512480.SH` 各 1,197 根日线，2021-10-08 至 2026-09-09，来源 `akshare:sina:v101`；
- 两只 ETF 各 49 条报价快照，最新源时间 2026-09-10 15:00:37+08，抓取时间 15:00:46+08；`is_realtime=false`，来源 `akshare:em:v101`，仍显示待资格核实；
- 切换前最近的 `refresh_market_context`、`refresh_news` 均为 `succeeded`，AKShare 新闻每次 200 条，Tushare 无凭据保持 `unsupported`。scheduler 已重启，下一次报价将在交易时段按既有 3 分钟节奏执行，收盘后再运行日线链路。

这次部署没有把旧日线提前改成当日收盘，也没有把公开报价时间戳宣称为实时。中证全指近期上下文、Sina 成交量、因子/预测资格、完整缠论、OCR/Vibe/真人模型、支付、自动训练和自动云地同步仍保持既有阻断边界。

## 首次切换时状态

公网首次切换到 v105 接收分支的 R1/R2/R3 修复代码。原工程 `E:\project\ETF-Fund-Analysis` 仍保持用户脏改动；`main` 未合并，标签未移动。

## 量能回退修复与生产重算（2026-09-11 22:25）

用户反馈“数据异常”后，复核线上快照确认根因是新浪历史回退把 `volume` 丢成 `None`，使 35 个标的全部触发 `volume_missing_for_shared_signals`。修复提交为 `208858e2e05b8ba6b31f7a4b85a9531044cc3e50`，应用实际版本字段仍为 1.0.4；归档 SHA-256 为 `a311c3cadea839013eaefdac03668eee0f84daee9be47ecb0f573169ea3640a1`。

修复只接受 `amount / volume` 与收盘价偏差不超过 10% 的新浪记录，来源标为 `akshare:sina:v102`；缺额或单位不自洽仍保留 `akshare:sina:v101` price-only。线上抽样 66,174 条新浪记录的最大偏差约 8.03%，超过 10% 的记录为 0。东财历史接口仍以 `ConnectionError` 回退新浪，失败原因和回退来源未被隐藏。

维护窗口先暂停 scheduler，使用生产 API 容器中的 `fund-decision run-task` 依次执行受审计任务：

- `refresh_bars`：35 个标的、无失败、`price_only=0`；
- `refresh_indicators`：35/35 创建成功，最新 `as_of_date=2026-09-11`；
- `refresh_forecasts`：140 条成功，仍为 `not_calibrated` 研究结果；
- `refresh_signals`：35 条成功，4 个“可试探”、31 个“观察”，`actionable=false`；
- `refresh_decision_board`：新快照 `4d1cab6fc596459c89a7eccc8f49691d`，`数据异常=0`，35 行统一标记 `quote_stale_at_snapshot_generation`，因为重算时间为 22:25 而最后公开报价为 15:01，实时资格仍未通过。

生产 PostgreSQL 只读复核显示 35 个启用标的成交量缺失行数为 0，日线最新日期均为 2026-09-11；scheduler 已恢复运行，API/worker healthy，公网 health 仍为 production、`public_composite`、认证开启。夜间页面继续显示 stale/未验证提示是报价时效和资格边界，不再代表量能数据丢失。

## 看板缓存修复与最终源码切换（2026-09-11 22:31）

用户继续反馈页面仍显示旧异常后，确认原版 WorkBuddy 的 legacy `api()` 未设置 `cache: no-store`，后端 `/api/bootstrap`、`/api/decision-board` 列表和详情也没有明确禁止缓存。修复提交为 `406cad001be8a90975e548e880dff12a5cc8c504`，归档 SHA-256 为 `2b6f73b6ae108b57c806d95671262007b83c7958df8d77d2212e8c0ddf9c8495`。

- 前端所有 legacy API/auth 读取固定 `cache: 'no-store'`；
- 后端 bootstrap、decision-board 列表和详情固定 `Cache-Control: private, no-store`；
- 新源码目录：`/opt/china-fund-decision/deploy-v105-406cad0`；诊断端口 `18084` 通过后切换；
- 切换前备份：`fund_decision_20260911_224106.sql.gz`，SHA-256 `1774355dcf38a5ad13590a9eb55f784f2f50fa3cd14f9c3a1c261ab6ab438c02`，权限 600；
- 切换后 API/worker healthy、scheduler running、公网 health 200、根页面 200；生产 PostgreSQL 未再次写入。

用户登录后重新加载页面会重新请求最新 `snapshot_id=4d1cab6fc596459c89a7eccc8f49691d`，不会继续使用旧浏览器缓存。整体 `stale` 仍只反映公开报价时间已过 8 分钟和实时资格未通过。
