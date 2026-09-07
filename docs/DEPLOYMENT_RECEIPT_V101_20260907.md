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

## 服务器盘点与当前边界

- SSH 只读盘点成功；生产目录当前仍运行旧 0.8.0 根 Compose（API 8080、旧 scheduler），迁移头为 `c2d3e4f5a6b7`。
- 生产数据库备份已由现有 Compose `db` 完成，备份权限 0600、sidecar SHA256 校验通过；备份内容未读取或传出。
- 尚未切换生产代码、数据库、Docker 容器、计划任务、反向代理或正式域名。必须先 staging 恢复/迁移、旧单位完整重抓、CI/PR 和维护窗口验收。

本收据只记录运行代码/环境事实，不把包内历史验证报告改写为本次生产成功证明。
