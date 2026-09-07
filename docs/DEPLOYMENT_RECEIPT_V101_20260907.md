# v1.0.1 接收与部署收据

日期：2026-09-07（Asia/Shanghai）。

## 接收

- ZIP：用户指定的 `ETF-Fund-Analysis_v1.0.1_full_20260907.zip`。
- SHA256：`EA1F2CDB8629C3E9598D1626A59FDDD03A5248E51F0D02CF22BB033B14334F49`，与预期一致。
- 归档项：562；`PACKAGE_MANIFEST_V101.json` 列出的 561 个文件全部匹配。
- 集成父提交：`9a0ca1812eda24acc390f1b3097662bfd615dfef`；原工程脏区未修改。
- 集成分支：`codex/v1.0.1-data-access`；远端已有 `codex/v1.0.1` 未重置。

## 本地与隔离验证

- 后端：812 收集、0 失败；5 个 Windows 符号链接/外部 PostgreSQL 条件跳过。
- 前端：Vitest 19、TypeScript、Vite build、旧 JS 19 通过。
- 标准浏览器：Playwright 5/5 通过；使用 18083 临时端口，因为 18082 被其他项目占用。
- 数据库/镜像：Alembic clean SQLite head `d40609090002`；PostgreSQL 16 条件测试 6 通过；Docker 镜像 build 与生产式 API smoke 通过。
- 静态安全：ShellCheck 9 脚本、Compose config、secret scan、`git diff --check` 通过。

## 数据源与真实任务

- AKShare 公共探测：两标的日线各 241 根，Sina 回退、成交量缺失；新闻可读；目录与公开 quote unavailable。
- Tushare：本次未读取或输出 Token，状态为未配置/未验证。
- FTShare：disabled/unqualified；RSS：未配置。
- 真实小样本任务仅处理 `510300.SH`、`512480.SH`，写入 562 根价格日线；缺量使指标、预测、信号和快照保持 `partial`/阻断，未用 Mock 补齐。

## 服务器盘点（部署前快照）

- SSH 只读盘点成功；生产目录当前仍运行旧 0.8.0 根 Compose（API 8080、旧 scheduler），迁移头为 `c2d3e4f5a6b7`。
- 生产数据库备份已由现有 Compose `db` 完成，备份权限 0600、sidecar SHA256 校验通过；备份内容未读取或传出。
- 以上是维护前快照；最终状态见下一节。旧生产报告与未跟踪目录未被覆盖。

本收据只记录运行代码/环境事实，不把包内历史验证报告改写为本次生产成功证明。

## 最终生产部署（2026-09-07）

- 本地提交 `224b59fb4215c3aeb93790144996575500eb5817` 已推送到 `codex/v1.0.1-data-access`；`ci` 与 `workspace-ci` 均成功。`main`、已有 `codex/v1.0.1` 分支和 v1.0.0 标签未改写。
- 生产数据库先用备份恢复到隔离 PostgreSQL，再由目标镜像执行 Alembic；生产 head 为 `d40609090002`。安全计数保留为 36 instruments、9851 daily bars、3 auth users、0 holdings、0 watchlist entries；OHLC 非法值 0、重复 instrument/date 0、成交量/额空值 0。
- 目标镜像标签为 `etf-workspace:v1.0.1-20260907`，镜像 digest `sha256:041f4b32b46c7b3af3fc3af3842f283b914633e1abdb67115260e78073c9834d`。部署覆盖文件 `deploy/compose.v101.production.yml` 的仓库/主机 hash 为 `102792def1359bb70d396783d02067b2a5cb27b572e0bb5d26499a0c3f15f57b`。
- 生产 API 与单 worker 均为 healthy，API 8080 保持回环端口；旧 API 与旧 scheduler 已停止，未启动第二个 scheduler。运行中的主机 Nginx 未重载，正式 HTTPS health 与首页均返回 200。
- 生产 PostgreSQL 备份 `fund_decision_20260907_181620.sql.gz` 保留在服务器，权限 0600、大小 6,873,325 bytes，SHA-256 `ea9c0fb369b7676db6c3cb976092d43635958426218e8224eabb158cc7eca347`；备份内容未读取或传出。配置、reports 和 Nginx 备份在 `backups/v101-predeploy-20260907/`。
- 真实 Provider 资格仍未晋级：AKShare Sina 日线两标的可读但成交量缺失，新闻可读，目录/公开 quote unavailable；Tushare 配置存在但本次目录、日线、现价、新闻均未通过；FTShare 未启用。生产使用 `public_composite`、`ALLOW_MOCK_FALLBACK=false`，不会用 Mock 补齐或生成操作级信号。
- 需要用户用既有账户登录正式站点；本次未创建/重置账户，也未读取或回显任何凭据。模型、OCR、分钟线和定时复盘保持关闭，后续需单独授权和资格验证。
