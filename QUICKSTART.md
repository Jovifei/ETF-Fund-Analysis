# 快速开始

## A. 先验证本地完整流水线

```bash
cd china-fund-decision-v2
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'

export APP_ENV=development
export AUTH_ENABLED=false
export MARKET_PROVIDER=mock
export DATABASE_URL=sqlite:///./fund_decision.sqlite3

fund-decision bootstrap --lookback-days 420
fund-decision run-task validate_forecasts
uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
```

检查：

```bash
curl -fsS http://127.0.0.1:8000/api/health
pytest -q
node --check backend/app/static/app.js
```

## B. 准备生产配置

```bash
cp deploy/.env.production.example .env
python scripts/generate_secrets.py
chmod 600 .env
```

必须修改：

- `POSTGRES_PASSWORD`
- `PRIVATE_ACCESS_TOKEN`
- `TUSHARE_TOKEN`
- `MARKET_PROVIDER=composite`
- `ALLOW_MOCK_FALLBACK=false`

使用 OpenAI-compatible 模型整理新闻时再配置：

```env
LLM_ENABLED=true
LLM_API_BASE=https://你的兼容端点/v1
LLM_API_KEY=...
LLM_MODEL=...
LLM_API_MODE=chat_completions
```

## C. 先做真实数据冒烟，不要直接开启调度器

```bash
docker compose build
docker compose up -d db api
docker compose run --rm api python scripts/provider_smoke.py
```

通过标准：

- 标的列表非空；
- 最近 45 天至少有约 15 根交易日 K 线；
- 盘中至少一部分标的确认 `realtime=true`；
- 没有使用 Mock；
- 数据源失败和备用切换都出现在审计记录中。

## D. 初始化并启动

```bash
docker compose run --rm api fund-decision bootstrap --lookback-days 900
docker compose up -d scheduler
docker compose ps
```

应用仅监听 `127.0.0.1:8080`。通过 SSH 隧道临时访问：

```bash
ssh -L 8080:127.0.0.1:8080 user@your-ecs-ip
```

浏览器访问 `http://127.0.0.1:8080`，输入 `PRIVATE_ACCESS_TOKEN`。

## E. 正式域名

配置 Caddy 或 Nginx 反向代理，启用 HTTPS。不要在 ECS 安全组开放 8080 或 5432。

## F. 首次上线后的检查

```bash
source .env
./scripts/smoke_http.sh
./scripts/backup_postgres.sh
docker compose logs --tail=200 api scheduler
```

在网页中检查：

- “数据源健康”中没有长期连续失败；
- 盘中实时行情数量符合预期；
- `not_calibrated` 没有被显示成已校准；
- Mock 警告不存在；
- 持仓录入后才出现“加仓/减仓”类状态；
- 信号状态不会在短时间内频繁往返。
