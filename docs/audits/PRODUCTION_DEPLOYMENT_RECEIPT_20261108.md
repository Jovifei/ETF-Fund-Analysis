# 生产部署收据 2026-11-08（e086e83）

## 结果

网站切换到提交 `e086e83`（docs 重组 `71d0ff3`/`1cfd971` + 腾讯历史传输守卫修复）的本机构建镜像。**数据库无迁移**：main 的 Alembic head 与生产库均为 `b7c8d9e0f1a2`，API 容器启动时的 `alembic upgrade head` 为无操作。API、worker 健康，scheduler 运行（`SCHEDULER_ENABLED=false` 与切换前一致，计算仍由本机定时任务承担）。策略、权重、Provider 选择、账户数据均未改动。

## 身份

- 新镜像：`china-fund-decision:deploy-e086e83`，image id `sha256:c43d755a104e0ae16859a9cf05707a068bc090055fcc97391d1e8c9b85830578`；本机 `docker save | gzip | ssh docker load` 传输，源与目标同一 image id。
- 旧镜像 `sha256:3b876da66381…`（tag `china-fund-decision:ci-8cceba1-pinned`）未删除；旧容器停止未删除，保留为回滚与取证资产。
- 编排：`/opt/china-fund-decision/etf-deploy-20261108/new.yml`，由 10-30 已验证规格派生，diff 仅两行（项目名、镜像引用），现场 `diff` 已留存于会话记录。
- 身份环境变量（`GIT_COMMIT_SHA`、`SHADOW_SYNC_CODE_SHA=a0d52e4…`、`SHADOW_SYNC_CONFIG_HASH=a12c6ea1…`）沿用 10-30 规格未改：它们描述展示包生产者身份，与本次应用镜像无关；沿用 10-31 先例。

## 备份

- `/opt/china-fund-decision/backups/fund_pre_e086e83_cutover_20261108_004936.dump`，443,740,141 字节，`sha256 aab72bdf82b0e8fa4486c62b564ad95ff2e45a48fe5c4e4568409d4ef0679a75`（`.sha256` 同目录）。
- TOC 完整性：容器内 `pg_restore -l` 读出 478 条条目。
- 未删除任何历史备份。磁盘 41G 中已用 81%，本次新增约 424 MiB。

## 镜像内验证（切换前）

- `akshare 1.20.35`（pyproject 未钉版本，pip 自由解析）。腾讯历史通道测试在镜像内 **11 passed**——10-31 收据记录的 akshare 钉层绕过不再需要，因为本次 `bounded_sdk` 守卫修复正确处理了新版显式 `timeout=None`。
- 镜像内 `alembic heads` = `b7c8d9e0f1a2`；`alembic check` 无待办变更。
- 沙盘演练（独立项目、网络 `10.248.100.0/24`、PG 16.15 副本库、独立端口）：`f0e1d2c3b4a5 -> b7c8d9e0f1a2` 升级成功；API `production` 模式健康，`auth_enabled=true`；未认证 holdings 401；`scripts/workspace_image_smoke.py` 通过（打包 Vue 深链 / CSP / 资产 immutable / 私有 API / 404 语义）。演练环境已销毁，未绑定生产端口或数据目录。
- 演练中确认生产必需项：`APP_ENV=production` 要求存在的 `OCR_TRANSIENT_ROOT`（tmpfs 提供）与合法 `OCR_MODE`；生产规格本就满足。

## 切换与即时核验

- 步骤：停旧三容器（保留）→ `compose --env-file .env -f new.yml up -d` → 等 API healthy → 功能检查 → 等 worker healthy。
- 容器：`etf-deploy-e086e83-api-1`（healthy，restarts=0）、`-worker-1`（healthy）、`-scheduler-1`（running，restarts=0）。
- 本机 8080：`{"status":"ok","version":"1.0.13","environment":"production","provider":"public_composite","auth_enabled":true}`；未认证 holdings 401。
- 公网 `https://etf.joviluma.com/`：200（1.58s）；`/api/health` 同上 JSON；未认证 holdings 401；CSP 头存在且 `script-src 'self'`。
- 日志：api 与 worker 自启动以来无 traceback / error 行。
- 展示包指针：`/app/.local/display-v113-a0d52e4` 下 `latest.json` 可读，接收历史含多条 sequence；未强制夜间重推旧数据冒充新鲜。

## 已知问题

- 旧栈 scheduler 容器在切换前约 3 小时以退出码 137 退出（服务器 1.87 GiB 内存压力所致，属切换前既有状况，与本次无关）。新栈 scheduler 已按规格运行；因 `SCHEDULER_ENABLED=false` 实际不执行任务。
- 服务器磁盘 81%（7.3 GiB 可用）。本次新增备份约 424 MiB；旧镜像与新镜像并存。后续发布前需评估保留策略（需 owner 授权，不自动清理）。
- `pyproject.toml` 仍未固定 `akshare`。本次守卫修复使新版可用，但依赖漂移风险仍在，是否钉版本留作独立决策。
- 邮件仍未配置；真实登录与手机验收、两个交易日自然运行仍待完成。

## 回滚

零迁移使回滚最简单：

```bash
cd /opt/china-fund-decision/etf-deploy-20261108
docker compose --env-file /opt/china-fund-decision/.env -f new.yml down
docker start etf-deploy-8cceba1-api-1 etf-deploy-8cceba1-worker-1
```

旧镜像与旧容器原样保留；数据库仍为 `b7c8d9e0f1a2`，旧镜像可直接读取，无需降级或迁移文件旁挂。cutover 脚本内置同一回滚路径（API 未及时 healthy 时自动执行）。
