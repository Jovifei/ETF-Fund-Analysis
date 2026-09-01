# Codex 部署任务清单

本文用于服务器上的 Codex。按顺序执行；失败时保留日志、停止下一阶段，不要用 Mock 或虚构结果掩盖问题。

## 0. 安全前置

- [ ] 阅读 `AGENTS.md`。
- [ ] 确认工作目录是用户私有仓库。
- [ ] 扫描仓库是否存在密钥：`.env`、历史提交、第三方 vendor、日志和报告。
- [ ] 不输出 `.env` 内容；日志只能说明某变量“已配置/未配置”。
- [ ] 确认 ECS 安全组未开放 5432、8080、Docker API 2375/2376。
- [ ] 确认 22 端口仅允许用户可信公网 IP；80/443 按是否启用域名开放。

## 1. 主机和容器环境

```bash
sudo bash deploy/aliyun/bootstrap_host.sh
sudo docker version
sudo docker compose version
```

- [ ] 记录 OS、CPU 架构、内存、磁盘空间，但不要记录实例密钥。
- [ ] 检查 NTP/时区为 `Asia/Shanghai`。
- [ ] 检查 Docker 日志轮转已由 Compose 配置。
- [ ] 若 Docker Hub 拉取缓慢，根据阿里云当前官方文档配置受信任的镜像加速，不要使用来源不明的镜像站。

## 2. 配置

```bash
cd /opt/china-fund-decision
cp deploy/.env.production.example .env
python3 scripts/generate_secrets.py
python3 scripts/generate_password_hash.py
chmod 600 .env
```

人工写入：

- [ ] `POSTGRES_PASSWORD`
- [ ] `AUTH_USERNAME`
- [ ] `AUTH_PASSWORD_HASH`（仅 Argon2id 哈希；不要保存明文密码）
- [ ] `AUTH_SESSION_SECRET`
- [ ] 可选 `AUTH_EMAIL`（仅同一账户登录别名；当前无 SMTP/OTP）
- [ ] `TUSHARE_TOKEN`
- [ ] `MARKET_PROVIDER=composite`
- [ ] `ALLOW_MOCK_FALLBACK=false`
- [ ] LLM 配置（初次数据验证时先保持 `LLM_ENABLED=false`）
- [ ] 可选 `NEWS_RSS_URLS`
- [ ] 若旧 CLI/API 仍需要 Bearer，再单独配置非占位符 `PRIVATE_ACCESS_TOKEN`；它不能用于浏览器登录。

禁止：

- [ ] 不把密钥复制进 YAML、Python 或 README。
- [ ] 不使用第三方仓库中出现的任何 Token。
- [ ] 不把生产 `.env` 提交 Git。

## 3. 静态和本地测试

```bash
pytest -q
python -m compileall -q backend/app
node --check backend/app/static/app.js
POSTGRES_PASSWORD=dummy docker compose config >/dev/null
```

- [ ] 全部通过。
- [ ] 生产反代必须覆盖客户端传入的 `X-Forwarded-For`，且 Compose 不启用 Uvicorn `--proxy-headers`；登录限流不得信任任意转发头。
- [ ] 若修改策略参数，更新版本号和测试，不得只改阈值。

## 4. 构建和数据库

```bash
docker compose build --pull
docker compose up -d db api
docker compose ps
docker compose logs --tail=150 api
```

- [ ] API health 为 `ok`。
- [ ] Alembic 已到 `head`。
- [ ] `docker compose exec db pg_isready` 成功。
- [ ] API 端口只绑定 `127.0.0.1`。
- [ ] PostgreSQL 没有 `ports:` 映射。

## 5. Tushare / AKShare 能力矩阵

```bash
docker compose run --rm api python scripts/provider_smoke.py | tee /tmp/provider-smoke.json
```

不得把输出中的潜在敏感参数上传。

需要记录到私有部署报告：

- [ ] `fund_basic` 是否可用；
- [ ] `fund_daily` 是否可用；
- [ ] 实时 ETF 接口究竟命中哪个 candidate；
- [ ] 实时行情中的代码、时间、价格、昨收、成交额、溢价率字段；
- [ ] 新闻接口是否可用；
- [ ] 交易日历是否可用；
- [ ] AKShare 备用接口是否从阿里云 IP 可达；
- [ ] 每个接口平均耗时和限频错误。

若实时行情没有得到执行级数据：

- [ ] 保持信号不可操作；
- [ ] 不把 `fund_daily` 最后一条改成 realtime；
- [ ] 选择有授权的数据源或仅做收盘研究版。

## 6. 自选池

编辑 `config/watchlist.json`：

- [ ] 删除纯演示标的或确认保留；
- [ ] 补充用户真实 ETF/LOF；
- [ ] 每只基金有一级/二级主题；
- [ ] 将沪深 300 ETF 保留为市场门控基准，或同时修改 `regime_benchmark`；
- [ ] 检查代码后缀 `.SH/.SZ`；
- [ ] 避免低流动性、长期停牌、濒临终止上市或无法获取可靠数据的标的。

随后：

```bash
docker compose run --rm api fund-decision run-task sync_instruments
docker compose run --rm api fund-decision bootstrap --lookback-days 900
```

## 7. 数据质量抽检

随机选择至少 5 只基金：

- [ ] 与另一可靠来源核对最近 20 日 OHLCV；
- [ ] 检查成交量/成交额单位；
- [ ] 检查复权口径；
- [ ] 检查停牌和缺口；
- [ ] 检查日线日期没有未来数据；
- [ ] 检查实时行情时间戳确为当天盘中；
- [ ] 检查 LOF 溢价率是否存在、单位是否为百分数。

任何字段不一致必须在 Provider Adapter 中解决，不能在信号层猜测。

## 8. LLM 新闻结构化

数据层稳定后再启用：

```env
LLM_ENABLED=true
LLM_API_BASE=...
LLM_API_KEY=...
LLM_MODEL=...
LLM_API_MODE=chat_completions
```

运行：

```bash
docker compose run --rm api fund-decision run-task refresh_news
```

- [ ] 验证 JSON Schema 支持；不支持时确认安全降级到启发式分析。
- [ ] 检查事实与推断分开。
- [ ] 检查恶意新闻正文中的“忽略指令/运行命令”等内容不会触发工具。
- [ ] 检查模型故障不会阻断行情和信号任务。
- [ ] 不把 API Key 输出到异常信息。

## 9. 预测验证

```bash
docker compose run --rm api fund-decision run-task validate_forecasts
```

- [ ] 检查方向准确率、Brier、MAE、80% 区间覆盖率和校准桶。
- [ ] 按 1/5/20 日分别评估。
- [ ] 使用按时间切分，不随机打乱。
- [ ] 确认训练样本特征只使用当时可知数据。
- [ ] 保留所有失败标的和原因。
- [ ] 在未完成至少一轮样本外评估前保持 `not_calibrated`。

## 10. 事件驱动轮动回测与独立复核

基础引擎已经实现，先运行：

```bash
docker compose run --rm api fund-decision run-task backtest_rotation
```

检查生成的 `rotation_backtest_*.json`：

- [ ] `decision_at=close_t`、`execution_at=open_t_plus_1`；
- [ ] 每条 decision 的 `feature_date_max` 不晚于决策日；
- [ ] 100 份整手、手续费、最低佣金和滑点已生效；
- [ ] 迟滞、主题分散、单基金上限和风险暴露门控已生效；
- [ ] 报告是否含 Mock；真实封版必须为 false；
- [ ] 极端单日收益 warning 已逐只核验复权/拆分；
- [ ] 总收益、回撤、Sharpe、换手与 510300 基准口径可复算。

Codex 仍需在独立分支补足并验证：

- [ ] 停牌和无成交；
- [ ] 涨跌停导致无法交易；
- [ ] 实际最小交易单位；
- [ ] LOF 溢价、申赎和限购风险；
- [ ] 现金收益；
- [ ] 独立向量化或 AKQuant/Backtrader 第二引擎；
- [ ] Train → Rolling → Holdout → Event-driven 四层结果；
- [ ] 不同费率、滑点和执行价格敏感性。

只有当独立引擎差异可解释且低于预设阈值，才能建立 sealed strategy；不得让回测任务自动改实时阈值。

## 11. 开启 scheduler

```bash
docker compose up -d scheduler
docker compose logs -f --tail=100 scheduler
```

观察至少一个完整交易日：

- [ ] 09:30～11:30 行情约每 3 分钟；
- [ ] 13:00～15:00 行情约每 3 分钟；
- [ ] 信号每 10～15 分钟；
- [ ] 午间不生成新的价格信号；
- [ ] 午间新闻按 10 分钟；
- [ ] 收盘后只执行一次日线/指标/预测/信号/报告；
- [ ] 手动任务与 scheduler 冲突时返回 409，而不是并发写库。

## 12. HTTPS 与访问控制

- [ ] 使用 `deploy/Caddyfile.example` 或 Nginx 示例。
- [ ] 启用 HTTPS。
- [ ] 浏览器使用账户密码登录；服务器仅保存 `AUTH_PASSWORD_HASH`（Argon2id）和 `AUTH_SESSION_SECRET`，HTTPS 下会话为 Secure HttpOnly SameSite cookie。
- [ ] `PRIVATE_ACCESS_TOKEN` 仅在旧 CLI/API 明确需要时保留为 Bearer 兼容凭据，不能作为浏览器身份。
- [ ] 可额外使用反向代理 Basic Auth 或仅通过 VPN/SSH 隧道。
- [ ] 检查浏览器 Network：SSE 与下载使用同源 cookie（无 URL Token、无 Authorization 会话令牌），非安全 cookie 请求包含 CSRF header。
- [ ] 检查 CSP、HSTS、nosniff、frame 和 referrer headers。

## 13. 备份与恢复

```bash
./scripts/backup_postgres.sh
sha256sum -c backups/*.sha256
```

- [ ] 配置每日 cron。
- [ ] 把备份同步到另一个存储位置；不能只留同一块云盘。
- [ ] 在临时数据库完整执行一次恢复。
- [ ] 记录恢复耗时和步骤。

## 14. 上线报告

在私有仓库创建 `deployment_reports/YYYY-MM-DD.md`，只写：

- 版本和 Git commit；
- ECS OS/架构，不写公网 IP 或实例密钥；
- 接口能力矩阵；
- 数据抽检结果；
- 测试和迁移结果；
- 预测验证状态；
- 未完成事项；
- 回滚点。

不得写任何 Token、Cookie、密码或长期签名 URL。
