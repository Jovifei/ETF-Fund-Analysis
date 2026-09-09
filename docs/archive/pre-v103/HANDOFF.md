# 接手入口：v1.0.1

先读 AGENTS.md、STATUS.md、docs/versions/V1.0.1.md、docs/DATA_ACCESS_V101.md、docs/VALIDATION_V101.md。

1. 基线9a0ca181属于codex/v1.0.0，核对时尚未合并main。不要从旧main覆盖新工作站；不要混用PR26/27/28的未完历史头。
2. 五档 current action、1/3/5/10 forecast、服务端确定性指标不变；数据单位变动有独立契约版本并进入config_hash。
3. 不读取/回显/复制凭据，不从Git历史恢复Tushare Token，不用LLM取数/算指标/下单。仅本人私有环境配置。
4. 更新真实数据先修复旧单位历史；没有完整覆盖不混合重算。GET只读，慢采集在有界单worker中执行。
5. 界面已经审核：保留Vue壳，新增matrix及原版入口；没有图1新附件时不能自称像素对照通过。
6. demo是临时Mock；live是真实provider+持久数据+认证+127.0.0.1，生产由独立Docker/PostgreSQL/TLS配置验收。不要把Git标签/CI当作用户机器部署证据。

修改后跑pytest、compileall、Vue19+新增用例、typecheck/build、原JS单测、Alembic、secret scan和标准Playwright。最终云端完整证据见docs/VALIDATION_V101.md，不能从历史数字抄写。

## 浏览器认证与持久数据库

正式部署维持 `AUTH_ENABLED=true`、`DATABASE_URL=<PostgreSQL URL>`、`AUTO_CREATE_SCHEMA=false`、`AUTH_COOKIE_SECURE=true`。
数据库备份与 Alembic 完成后，在部署主机交互运行 `fund-decision auth-bootstrap-admin`。
HttpOnly / SameSite Cookie + CSRF 是浏览器认证权威；不得在 localStorage 保存令牌或恢复旧 Bearer 登录路径。
仅 `scripts/run_workspace_live.py` 的认证回环 HTTP 使用 `AUTH_COOKIE_SECURE=false`；它不是公网生产配置。

## 本次接收复验（2026-09-07）

ZIP `EA1F2CDB8629C3E9598D1626A59FDDD03A5248E51F0D02CF22BB033B14334F49` 与预期一致；从 `9a0ca181` 建立 `codex/v1.0.1-data-access` 并移植 1.0.1 包。Windows 全量 pytest 为 812 收集、0 失败、5 个权限/外部 PostgreSQL 条件跳过；新增专题 28 通过；前端 19、Playwright 5、PostgreSQL 6、Docker 镜像 smoke 通过。Matrix 表头和浏览器 fixture 的两个必要修复已包含在工作树。

## 生产部署前快照（已完成）

远端只读盘点当时显示生产为 0.8.0 根 Compose、API 8080 与旧 scheduler，迁移头 `c2d3e4f5a6b7`；生产备份已由既有脚本完成并通过 SHA256/0600 校验。以下“尚未切换”只描述该时点；最终状态见下一节。未读取 `.env`、Token、Cookie、密码、持仓或备份内容。

## 生产部署完成（2026-09-07）

上述段落是部署前快照。其后已完成：从备份恢复到隔离 PostgreSQL 并迁移到 `d40609090002`；提交 `224b59f` 推送到 `codex/v1.0.1-data-access`，`ci` 与 `workspace-ci` 成功；目标镜像 `etf-workspace:v1.0.1-20260907` 已加载。

正式站点当前由 `deploy/compose.v101.production.yml` 运行 v1.0.1 API 与单 worker，内部/HTTPS health 均为 200，旧 API 与旧 scheduler 停止，Nginx 未重载。Provider 采用 `public_composite` 且 `ALLOW_MOCK_FALLBACK=false`；AKShare Sina 日线缺量、Tushare 权限探测未通过，故新衍生信号仍 fail-closed。不得把这些降级数据写成完整实时或 calibrated 资格。

生产备份和配置归档保留在服务器 `backups/v101-predeploy-20260907/`；不要读取或回显其内容。回滚优先停止 v1.0.1 API/worker、恢复旧 API/scheduler，然后按备份与迁移审计决定是否恢复数据库；不要直接执行 `volume *= 100` 或删除旧报告。
