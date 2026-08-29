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

## B. 生产环境配置

```bash
cp deploy/.env.production.example .env
python3 scripts/generate_secrets.py
chmod 600 .env
```

必须修改 `POSTGRES_PASSWORD`、`PRIVATE_ACCESS_TOKEN`、`TUSHARE_TOKEN`（如使用 Tushare）。生产保持 `MARKET_PROVIDER=composite`、`ALLOW_MOCK_FALLBACK=false`。

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

反向代理必须设置 12MB body limit（Caddy `request_body max_size 12MB` 或 Nginx `client_max_body_size 12m`），以覆盖 10MiB 图像上限和 multipart 开销。

## D. 迁移、备份与部署

生产上线前备份数据库，再执行三项增量迁移：

```text
158ca7025305 (initial)
  -> 9f1c2b3a4d5e (multi-model analysis)
  -> a2b3c4d5e6f7 (market context)
  -> b3c4d5e6f7a8 (holding import OCR)
```

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

## F. 明确边界

发行版本为 `0.7.0`；策略版本仍为 `signal-v0.4.0`，指标/预测版本仍由 `config/strategy.json` 管理。本版本不声称真实数据稳定、预测 calibrated、部署完成或可执行交易；本项目没有自动交易功能。
