# 快速开始

## A. 本地 Mock 验证

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
export APP_ENV=development AUTH_ENABLED=false MARKET_PROVIDER=mock
export DATABASE_URL=sqlite:///./fund_decision.sqlite3
fund-decision bootstrap --lookback-days 420
fund-decision run-task refresh_market_context
fund-decision run-task validate_forecasts
uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
```

本地检查：

```bash
curl -fsS http://127.0.0.1:8000/api/health
pytest -q
python -m compileall -q backend/app
node --check backend/app/static/app.js
```

Mock 只证明本地流水线和页面行为；Mock/不可用数据永远不可产生 actionable 信号。

### 安全演示模式

登录后进入「系统」，选择「演示数据 · 隔离 Mock」，点击「加载演示数据」。演示服务使用进程内
SQLite 和 420+ 天合成日线，不访问外网、不写正式 PostgreSQL、持仓、审计或报告目录；结果固定为
`DEMO`、`is_mock=true`、`research_only=true`、`actionable=false`。演示期间正式任务和持仓变更按钮会被
禁用；点击「退出演示并恢复正式数据」即可返回正式看板。重启 API 后演示数据消失。

正式看板的「更新日线」默认回看 120 个自然日（约 80 个交易日），避免只取 30 个自然日而不足以
计算 30 根交易日指标。页面状态区分「待初始化」「历史数据不足」「数据源不可用」和「数据异常」；
只有已有足够历史而核心指标计算失败时才会显示「数据异常」。

### FTShare 备用源

FTShare 是可选、只读的公开数据备用源，默认不启用，也不需要 Token。免费档仍为 AKShare 主源；如已配置 Tushare Token，Tushare 仅作为第二候选；
只有运行 `scripts/qualify_ftshare.py` 得到合格报告、确认独立的数据服务条款，并在服务器 `.env`
明确设置 `FTSHARE_QUALIFICATION=qualified` 与 `FTSHARE_ENABLED=true` 后，FTShare 才会加入最后备用链。
详见 [`docs/FTSHARE_PROVIDER.md`](docs/FTSHARE_PROVIDER.md)。

## B. 生产环境配置

```bash
cp deploy/.env.production.example .env
python3 scripts/generate_secrets.py
python3 scripts/generate_password_hash.py
chmod 600 .env
```

必须修改 `POSTGRES_PASSWORD`、`AUTH_USERNAME`、`AUTH_PASSWORD_HASH`、`AUTH_SESSION_SECRET` 与 `TUSHARE_TOKEN`（如使用 Tushare）。
`generate_password_hash.py` 隐藏输入密码，只输出 Argon2id 哈希；`generate_secrets.py` 输出数据库密码和会话密钥。生产保持
`AUTH_COOKIE_SECURE=true`、`MARKET_PROVIDER=composite`、`ALLOW_MOCK_FALLBACK=false`。`AUTH_EMAIL` 只是同一账户的可选登录别名，
本版本不发 SMTP 邮件或 OTP。`PRIVATE_ACCESS_TOKEN` 可留空；若为旧 CLI/API 保留，使用 `Authorization: Bearer`，不再用于浏览器登录。

### 单一分析 provider

默认关闭。若人工决定启用 Codex/OpenAI Responses，只在服务器 `.env` 配置：

```env
ANALYSIS_ENABLED=true
ANALYSIS_PRIMARY_PROVIDER=codex_openai_responses
ANALYSIS_PRIMARY_MODEL=<server-local-model-id>
ANALYSIS_PRIMARY_MODE=responses
OPENAI_API_KEY=<server-local-secret>
ANALYSIS_CODEX_BASE_URL=https://api.openai.com/v1
ANALYSIS_CODEX_ENABLED=true
```

Anthropic/DeepSeek 只能手工切换为唯一主 provider；不配置则禁用。任何 provider 错误都不会静默 failover。模型无工具、凭据、数值决策或券商权限；Codex/Claude Code 只能异步生成只读审阅候选，人工显式接受后才记录。

## C. OCR 操作与资格门槛

Pillow 核心校验 PNG/JPEG/WebP。默认 `OCR_MAX_IMAGE_BYTES=10485760`（10 MiB）、12,000×12,000、4,000 万像素、`OCR_TIMEOUT_SECONDS=60`、`OCR_TRANSIENT_TTL_MINUTES=15`。PaddleOCR 可选但当前环境未取得真实包/模型资格；只有 Python 3.12/Linux、`paddle-local-v1` manifest（路径、大小、SHA-256）和私有只读模型根目录都验证后才可启用。Docker 镜像不会安装重型 Paddle，缺少合格模型时 API 返回 503/unavailable，不伪装成功。

生产 Windows OCR fail-closed。Linux 上 `OCR_TRANSIENT_ROOT` 须为独立 0700 私有目录，模型根目录私有只读。上传 → 本地 OCR → 候选编辑/拒绝 → 显式确认；确认前不写持仓。云复核默认关闭，只有用户明确同意才可发起；当前版本关闭出网，不自动重试。

反向代理必须设置 12MB body limit（Caddy `request_body max_size 12MB` 或 Nginx `client_max_body_size 12m`），以覆盖 10MiB 图像上限和 multipart 开销。Nginx 必须以 `$remote_addr` 覆盖而不是追加 `X-Forwarded-For`；Compose 已禁用 Uvicorn proxy-header trust，登录限流不会信任客户端自带的转发链。

## D. 迁移、备份与部署

生产上线前备份数据库，再执行当前完整增量迁移链：

```text
158ca7025305 (initial)
  -> 9f1c2b3a4d5e (multi-model analysis)
  -> a2b3c4d5e6f7 (market context)
  -> b3c4d5e6f7a8 (holding import OCR)
  -> c4d5e6f7a8b9 (forecast corridor provenance)
  -> d5e6f7a8b9c0 (calibration profiles, current head)
```

The disposable SQLite exercise now passes `alembic upgrade head`, `current`, full `downgrade base`/re-upgrade, and `alembic check` at this head.  Its audited ORM reconciliation preserves the historical review/analysis hash-check names, opaque import-session constraint, nullable legacy calibration JSON, and unique `candidate_id` lookup contract.  This local evidence does not replace the required real PostgreSQL upgrade/downgrade/backup-restore qualification.

```bash
./scripts/backup_postgres.sh
alembic upgrade head
sudo bash deploy/aliyun/deploy.sh
```

回滚前必须验证备份 SHA-256 和隔离恢复；不得直接改生产数据库。API 监听 `127.0.0.1:8080`，scheduler 每 30 秒检查任务到期，市场上下文默认 15 分钟。

## E. 真实 Provider 冒烟

先只启动 `db api`，再运行：

```bash
docker compose build
docker compose up -d db api
docker compose run --rm api python scripts/provider_smoke.py
```

没有非空标的、可审计的来源/时间、新鲜实时字段和无 Mock 证据时，不要开启 scheduler。真实 PostgreSQL、Tushare/AKShare、OpenAI、Paddle wheel/model、ECS 和 HTTPS 仍需分别资格验证。

## G. 本地 Docker 验证（上 ECS 前）

先在本地用 Docker 跑通 PostgreSQL + API，确认无问题后再部署服务器。

```bash
# 1. 准备配置（Windows PowerShell 或 Git Bash 均可）
cp deploy/.env.local.docker.example .env
python scripts/generate_secrets.py        # 将输出填入 POSTGRES_PASSWORD / AUTH_SESSION_SECRET
python scripts/generate_password_hash.py  # 将唯一输出填入 AUTH_PASSWORD_HASH，并设置 AUTH_USERNAME
# 编辑 .env：前期测试用 MARKET_PROVIDER=akshare（免费东财公开接口，TUSHARE_TOKEN 可留空）
# 保持本机 HTTP 模板的 APP_ENV=development 与 AUTH_COOKIE_SECURE=false；生产 HTTPS 使用 production 模板并设为 true。
# Token 也可登录后在「系统 → 行情数据源」保存；完整档才会启用 Tushare

# 2. 构建并启动（先不启 scheduler）
docker compose build
docker compose up -d db api
docker compose ps
docker compose logs --tail=100 api

# 3. 健康检查
curl -fsS http://127.0.0.1:8080/api/health
# 可选旧 Bearer API 访问（仅兼容 CLI；浏览器使用账户密码会话）
curl -fsS -H "Authorization: Bearer <PRIVATE_ACCESS_TOKEN>" http://127.0.0.1:8080/api/instruments

# 4. Provider 冒烟（需 TUSHARE_TOKEN）
docker compose run --rm api python scripts/provider_smoke.py

# 5. 数据管道（Token 配置后）
docker compose run --rm api fund-decision run-task sync_instruments
docker compose run --rm api fund-decision bootstrap --lookback-days 900

# 6. 确认无误后再启 scheduler
# 编辑 .env：SCHEDULER_ENABLED=true
docker compose up -d scheduler
```

本地 Docker 默认建议：

- `SCHEDULER_ENABLED=false`（数据资格通过前）
- `OCR_MODE=disabled`（未 provision Paddle 模型前）
- API 绑定 `127.0.0.1:8080`，PostgreSQL 不映射宿主机端口
- 浏览器访问：http://127.0.0.1:8080/ 。登录框填写 `AUTH_USERNAME` 或可选 `AUTH_EMAIL` 与原始密码；密码、会话和旧 Bearer 凭据不会写入 localStorage。Docker 本机 HTTP 模板设 `AUTH_COOKIE_SECURE=false`；生产 HTTPS 必须为 `true`。不提供 SMTP/邮件 OTP。
- 页签含「ETF信号分级」（研究五档宽表）。静态资源在镜像内，改 HTML/JS/CSS 后需 `docker compose build api` 再起；`config/` 一般已 volume 挂载。

## F. 明确边界

发行版本为 `0.7.0`；策略版本见 `config/strategy.json`（当前 `signal-v0.7.0-research` 等）。本版本不声称真实数据稳定、预测 calibrated、部署完成或可执行交易；本项目没有自动交易功能。
