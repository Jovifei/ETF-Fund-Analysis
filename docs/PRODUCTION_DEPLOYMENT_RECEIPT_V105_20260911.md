# v1.0.5 接收分支公网部署收据（2026-09-11）

## 授权与保护

Jovi 在本轮明确要求继续修复并部署到公网生产。部署使用独立接收分支和新源目录，没有覆盖原工程脏改动，没有重置、清空或初始化生产 PostgreSQL、账户、持仓和自选数据。

- 接收分支：`codex/v105-handoff-local-20260910`
- 部署前代码 HEAD：`409a5e5b28cba190736ca930eba80702f74b4317`
- 固定基线：`46c713d4a7f6f247461ec9b075948f25c6741df7`
- 服务器归档：`/opt/china-fund-decision/deploy-v105-409a5e5`
- 归档 SHA-256：`e7830c4831754fc583070ee057cce98ae2a306be839229a71b1581a5c9dc71cc`
- 运行镜像：既有 `etf-workspace:v1.0.4-runtime-20260910`；本轮没有在服务器直接 build。

## 备份与回滚

切换前通过现有备份脚本生成：

- `/opt/china-fund-decision/backups/fund_decision_20260911_084351.sql.gz`
- SHA-256：`cd2e8088d8c058778399763ec1bc68e060cfb480aa1eb08a74c6f27464a58d8c`
- 权限：`600`，大小 `17,597,701` bytes

旧 v1.0.4 运行目录 `deploy-v104-3e4b9fa-r2`、旧 Compose、旧镜像和精确回滚文件 `compose.production.v104-3e4b9fa-r2.rollback.yml` 均保留。新 Compose 使用独立项目名和容器名，失败路径为停止 v105、启动该回滚 Compose。

## 灰度与切换证据

1. 远端 `docker compose config -q` 通过。
2. 诊断 Compose 在 `127.0.0.1:18081` 以 v105 源挂载启动；Alembic 使用 PostgreSQL 连接并无待迁移，API health 返回 production、`public_composite`、认证开启；诊断容器已清理。
3. 正式切换先停止 v1.0.4 三容器，再启动 `etf-workspace-v105-production-api/worker/scheduler`。
4. 切换后 API、worker healthy，scheduler 运行；内部和公网 `https://etf.joviluma.com/api/health` 均返回 `status=ok`、`version=1.0.4`、`environment=production`、`provider=public_composite`、`auth_enabled=true`。
5. 公网根页面 HTTP 200（568 bytes）；未登录访问受保护的 `/api/workspace/data-health` 返回 401，认证门禁仍在。

生产环境显式保持 `ALLOW_MOCK_FALLBACK=false`、`AUTH_ENABLED=true`、`SCHEDULER_ENABLED=true`、`BALANCED_REFRESH_ENABLED=false`、`WORKSPACE_DISCOVERY_ENABLED=false`、模型/OCR/Bridge/每日复盘关闭。应用版本字段仍为仓库实际的 `1.0.4`，没有把接收批次名称伪装成不存在的应用版本。

## 数据与持久性复核

切换后只读查询生产 PostgreSQL：`auth_users=3`、`holdings=0`、`user_watchlist_entries=6`，数据库约 52 MB，未出现账户或个人数据重置。

切换时服务器本地时间为 `2026-09-11T08:52:20+08:00`，尚未进入 A 股盘中报价窗口；已有两只 ETF 数据保持：

- `510300.SH`、`512480.SH` 各 1,197 根日线，2021-10-08 至 2026-09-09，来源 `akshare:sina:v101`；
- 两只 ETF 各 49 条报价快照，最新源时间 2026-09-10 15:00:37+08，抓取时间 15:00:46+08；`is_realtime=false`，来源 `akshare:em:v101`，仍显示待资格核实；
- 切换前最近的 `refresh_market_context`、`refresh_news` 均为 `succeeded`，AKShare 新闻每次 200 条，Tushare 无凭据保持 `unsupported`。scheduler 已重启，下一次报价将在交易时段按既有 3 分钟节奏执行，收盘后再运行日线链路。

这次部署没有把旧日线提前改成当日收盘，也没有把公开报价时间戳宣称为实时。中证全指近期上下文、Sina 成交量、因子/预测资格、完整缠论、OCR/Vibe/真人模型、支付、自动训练和自动云地同步仍保持既有阻断边界。

## 当前状态

公网已切换到 v105 接收分支的 R1/R2/R3 修复代码。原工程 `E:\project\ETF-Fund-Analysis` 仍保持用户脏改动；`main` 未合并，标签未移动。后续观察重点为 09:30 后报价 scheduler 审计、收盘后的 `refresh_bars` 和页面实际时间显示。
