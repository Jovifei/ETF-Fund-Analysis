# v1.0.4 公网生产部署收据（2026-09-10）

## 授权与边界

Jovi 在本轮明确授权修复数据刷新问题并部署到 `https://etf.joviluma.com` 公网生产。部署前保留原生产运行目录、旧镜像和 PostgreSQL 备份；没有重置、清空或初始化用户账户、持仓、数据库，也没有把 Mock 或未验证数据写成实时数据。

## 交付物

- 应用提交：`3e4b9fa`，接收分支 `codex/v104-news-time-review-20260910`，已推送远端；`main` 未合并。
- 服务器源归档：`deploy-v104-3e4b9fa-r2`；归档 SHA-256：`6AD49695E787CD3BEF7B76B24E64DEBF3CC56B9408E6EB35E205E6A717FB8E8F`。
- 运行镜像：`etf-workspace:v1.0.4-runtime-20260910`。它以既有 v1.0.1 运行时为基底，在无网络构建中加入 `cryptography 46.0.7`；wheel SHA-256 为 `420B1E4109CC95F0E5700EED79908CEF9268265C773D3A66F7AF1EEF53D409EF`。
- PostgreSQL 备份：`fund_decision_20260910_133758.sql.gz`，SHA-256：`a83cd01977a9636caaac46b7b09e13f1f676841cf3ab35254b5bf9e102ac21cb`，文件权限为 600。

## 切换步骤与运行状态

1. 使用现有 `backup_postgres.sh` 完成备份并记录 hash。
2. 在服务器新增源目录和运行时叠加镜像，未覆盖旧目录。
3. 用独立诊断端口验证 `version=1.0.4`、生产环境、真实 provider 和认证开关。
4. 滚动重建 API，再启动 worker 和 scheduler；失败路径会停止新容器并恢复旧 Compose。
5. 重启后再次确认 worker healthy、scheduler running、内部和公网 health 均返回 1.0.4。

生产容器当前均使用 `etf-workspace:v1.0.4-runtime-20260910`：API healthy、worker healthy、scheduler running。公网 `GET /api/health` 返回 `status=ok`、`version=1.0.4`、`environment=production`、`provider=public_composite`、`auth_enabled=true`。生产配置保持 `ALLOW_MOCK_FALLBACK=false`、`SCHEDULER_ENABLED=true`、模型/OCR/Bridge/每日复盘关闭；AKShare bounded timeout 显式为 60 秒。

回滚材料仍保留：旧 v1.0.4 源目录 `deploy-v104-7bc6c43`、回滚 Compose `compose.production.v104-7bc6c43.rollback.yml`、旧 v1.0.1 容器和镜像均未删除。当前旧 v1.0.1 API/worker 为停止状态。

## 数据刷新证据

- scheduler 在 14:29:55 执行 `refresh_quotes`，14:30:19 成功结束；`requested=35`、`received=35`、失败为空，provider audit 为 `akshare/fetch_spot_quotes/ok`。
- 连续性复核显示 14:35、14:40、14:45 的决策板刷新均成功，14:35/14:40/14:45 的 `fetch_spot_quotes` provider audit 均为 `ok`；最新检查时两只 ETF 报价已到 14:45 左右。
- `510300.SH` 最新报价时间为 14:30:07，`512480.SH` 为 14:30:01；两者均写入生产 PostgreSQL。AKShare 的公开时间戳尚未完成实时资格认证，记录保留 `is_realtime=false` 和 `public_quote_not_qualified`，页面不会误报为实时。
- 受审计 `TaskService` 任务 `refresh_bars` 只针对两只 ETF 执行，14:32:41–14:32:52 完成，`inserted=2`、`failures=[]`；两只 ETF 均为 1,197 根日线，日期 2021-10-08 至 2026-09-09。东财历史调用失败后按既有契约使用 Sina 价格回退，成交量保持缺失，未补零。
- 三个指数缓存（上证、沪深300、中证全指）均为 1,197 根 OHLC，`source_as_of=2026-09-09`；中证全指没有复制 ETF 或点值，仍按真实 OHLC 缓存和资格边界展示。
- 新闻 scheduler 任务成功；Tushare 因无凭据保持 `CapabilityUnavailable`，不影响 AKShare 新闻路径。

## 根因与修复

刷新失败的直接根因是 AKShare ETF 现货接口需要约 18 秒完成 16 页分页，原 `BoundedSDK` 20 秒硬截止会叠加进程启动和序列化时间而误判 `ProviderTimeout`。把公开源预算统一提高为 60 秒后，单只 ETF、全量启用标的和 scheduler 自动任务均可成功返回。修复已加入配置默认值、示例配置和回归测试 `test_default_akshare_budget_covers_paged_public_spot_endpoint`。

## 验证与剩余边界

- 接收分支全套 `pytest -q` 通过（仅现有平台/数据库条件跳过和依赖弃用警告）；新增数据访问回归通过。
- `compileall`、`node --check backend/app/static/app.js`、旧 WorkBuddy JS 15/15 和 `git diff --check` 通过。
- 真实生产页面的报价现在可见当日盘中快照；日线是最近已完成交易日，当前交易日收盘后由 scheduler 的 `refresh_bars` 写入，不提前把盘中值冒充日线收盘。
- 公开 AKShare 时间戳、Sina 成交量、因子诊断资格、中证全指实时资格、OCR/Vibe/真人模型、自动云地同步、支付订阅和完整缠论仍未通过相应门禁；这些边界没有因部署成功而改变。

后续观察点是收盘后的 `refresh_bars`、指标和报告链路，以及下一轮报价是否持续成功。若 provider 退化，审计和页面应继续显示失败/待核实状态，保留历史缓存并按回滚流程处理。
