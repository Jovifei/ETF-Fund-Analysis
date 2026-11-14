# 生产部署收据 2026-11-09（0e2f888）

## 结果

网站成功切换到提交 `0e2f888`（板块研判与结构因子落地：P0 基线与链路核查 + P1 结构因子审核修复 + P2 代表 ETF 映射 + P3 展示包图表扩展 + P4 前端 SectorDrawer 抽屉集成 + P5 全量测试验证 + P6 生产平滑切流）的本机构建镜像。

**数据库零迁移**：Alembic head 与生产库一致保持在 `b7c8d9e0f1a2`，容器启动时 `alembic upgrade head` 为无操作（0 migrations）。API 与 Worker 健康检查均进入 `healthy`，Scheduler 容器保持就绪状态（`SCHEDULER_ENABLED=false`，实际低频分析由本机计算生产者运行）。公网 HTTPS、CSP 安全响应头、未认证 401 守卫、板块代表映射与图表前端渲染全部通过验收。

## 身份与镜像

- **目标提交**: `0e2f88832cfbac30a7dccc87c00148548940fe14`
- **Git Tree**: `bfd9665243b52c127d10727e66910158c8a6e090`
- **发布分支**: `codex/sector-drawer-v1-20261108`（基于 `main` 提交 `3ce3a74`）
- **镜像标签**: `china-fund-decision:deploy-0e2f888`
- **镜像配置哈希**: `sha256:251709d87ef4f6aaee6c416936b0c995a5be96d296f486ca870386abaa8cc778`
- **传输方式**: 本机构建 Docker 镜像 -> `docker save` 归档 -> SCP 高通量传输至阿里云 ECS -> 宿主机 `docker load`。
- **保留前序镜像**: `china-fund-decision:deploy-e086e83`（Image ID `sha256:c43d755a104e...`）与停止状态的旧容器完整保留，绝不擅自删除。
- **编排文件**: `/opt/china-fund-decision/etf-deploy-20261109/new.yml`。
- **展示包生产者身份**: 严格遵循系统架构解耦规范，生产环境环境变量 `SHADOW_SYNC_CODE_SHA=a0d52e4...` 与 `SHADOW_SYNC_CONFIG_HASH=a12c6ea1...` 继续维持既有展示包消费口径，不冒充生产者。

## 数据库备份

- **备份文件**: `/opt/china-fund-decision/backups/fund_pre_0e2f888_cutover_20261109_215849.dump`
- **文件大小**: 444,570,891 字节（~424 MiB）
- **SHA256**: `c3838e3b2d5361f0f29cd4dacd0283f708dc2fa288fb467166e287f7629e93a9`（伴生 `.sha256` 校验文件已落盘）
- **TOC 条目数**: 478 条（`pg_restore -l` 严格核对，与切流前结构完全一致）
- **未删除任何历史资产**: 历史备份全部完整封存。

## 切换执行与即时核验

- **切流脚本**: `/opt/china-fund-decision/etf-deploy-20261109/cutover.sh`（执行退出码：0）
- **容器状态**:
  - `etf-deploy-0e2f888-api-1`: Up / `healthy` / RestartCount=0 / 监听 `127.0.0.1:8080->8000/tcp`
  - `etf-deploy-0e2f888-worker-1`: Up / `healthy` / RestartCount=0
  - `etf-deploy-0e2f888-scheduler-1`: Up / RestartCount=0
- **本地回环接口核验**:
  - `GET http://127.0.0.1:8080/api/health` -> `200 OK` (`{"status":"ok","app":"ETF Fund Decision","version":"1.0.13","environment":"production","provider":"public_composite","auth_enabled":true}`)
  - `GET http://127.0.0.1:8080/api/workspace/holdings` -> `401 Unauthorized`
  - `GET http://127.0.0.1:8080/api/workspace/sectors/representatives` -> `401 Unauthorized`
  - `GET http://127.0.0.1:8080/api/workspace/research/overview` -> `404 Not Found`（未挂载展示包时语义正确）
- **公网 HTTPS 验证 (`https://etf.joviluma.com/`)**:
  - `HTTP/2 200 OK`
  - Content-Type: `text/html; charset=utf-8`
  - 静态资源入口已更新为最新打包 Vue SPA：
    - `<script type="module" crossorigin src="/workspace-assets/index-CHtYdf1l.js"></script>`
    - `<link rel="stylesheet" crossorigin href="/workspace-assets/index-D1V9ge67.css">`
  - 静态资源缓存控制：`cache-control: public, max-age=31536000, immutable`
  - 安全头：
    - `content-security-policy: default-src 'self'; base-uri 'self'; object-src 'none'; frame-ancestors 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; form-action 'self'`
    - `strict-transport-security: max-age=31536000; includeSubDomains`
    - `x-content-type-options: nosniff`
    - `x-frame-options: SAMEORIGIN`
- **容器运行日志**:
  - `api-1`: alembic check clean, uvicorn running, 无任何 unhandled exception 或 traceback。
  - `worker-1`: 健康探针正常响应。
  - `scheduler-1`: 正常处于等待状态，无异常退出。

## 零迁移秒级回滚路径

若需紧急回滚，旧容器与旧镜像均保持原始状态未删除，执行以下命令即可在数秒内切回前序版本：

```bash
cd /opt/china-fund-decision/etf-deploy-20261109
docker compose --env-file /opt/china-fund-decision/.env -f new.yml down
docker start etf-deploy-e086e83-api-1 etf-deploy-e086e83-worker-1 etf-deploy-e086e83-scheduler-1
```
