# 中国 ETF / LOF 私有决策看板

一个面向中国场内 ETF/LOF 的**个人私有研究系统**。它把行情、日线、技术指标、主题新闻、持仓和多期限预测整理成可审计的信号看板，并按北京时间自动刷新。

当前版本：`0.4.0`

> 本项目不连接券商、不自动下单。技术指标、仓位约束和信号状态由确定性程序计算；OpenAI-compatible 模型仅用于把新闻整理成结构化事实、推断和风险项。预测基线默认处于 `not_calibrated`，在完成真实数据的 walk-forward 验证前，不应作为确定性收益判断。

## 已实现

- Tushare 主数据源、AKShare 备用源，禁止生产环境静默回退到 Mock。
- 可选 RSS/Atom 新闻源，兼容自建 RSSHub 路由。
- ETF/LOF 自选池、日线、盘中快照、数据源审计和退化标记。
- MA、MACD、KDJ、RSI、ATR、BOLL、量比、收益/波动/回撤、TD Setup。
- 1、5、20 个交易日相似样本预测：上涨概率、期望值、Q10/Q50/Q90、样本数和置信度。
- 手工 walk-forward 预测验证：方向准确率、Brier、MAE、区间覆盖率和校准桶。
- 事件驱动 ETF 轮动回测：收盘决策、次日开盘执行、整手、费率、滑点、迟滞、主题分散和市场暴露门控。
- 结合持仓成本、当前权重、目标权重的信号状态机。
- 以沪深 300 ETF 为代理的市场风险门控和组合总暴露上限。
- 信号迟滞：最短状态持续时间和最小分数变化，避免频繁反转。
- 单基金上限、单主题上限、单次调整上限。
- 新闻去重、主题映射、提示注入隔离和 Pydantic JSON 校验。
- 暗色网页看板、K 线/MACD Canvas 图、持仓录入、SSE 增量更新、HTML 报告。
- PostgreSQL、Alembic、FastAPI 和独立调度进程。
- Docker Compose、阿里云 ECS 部署脚本、备份/恢复、CI 和 Codex 交接规范。

## 设计原则

```text
外部数据源
   ↓
原始记录 + 来源 + 时间 + 质量哈希
   ↓
确定性指标 / 新闻结构化 / 预测基线
   ↓
实际输入体检（核心数据缺失即阻断）
   ↓
基金质量 + 主题 + 市场状态 + 持仓约束
   ↓
版本化信号快照和证据
   ↓
FastAPI / SSE / HTML 报告
```

项目吸收了 GitHub 社区中若干成熟思路，但没有让第三方仓库直接进入生产依赖：

- `fund-rotation-analyst`：审计优先缓存、主题分类、多维基金评分。
- `vibe-astock`：硬指标不经过 AI、实际输入体检、退化数据显式警告。
- `etf-rotation-strategy`：WFO→向量化→事件驱动验证、迟滞、波动率仓位门控、参数冻结。
- `fund-analysis-matrix`：暗色卡片布局、自选池和图表详情交互。
- `RSSHub`：通过标准 RSS/Atom 接口扩展新闻源的思路。

具体来源、版本和风险见 [`docs/GITHUB_RESEARCH.md`](docs/GITHUB_RESEARCH.md) 与 [`vendor/manifest.json`](vendor/manifest.json)。

## 目录

```text
backend/app/               FastAPI、数据层、指标、预测、信号与静态看板
backend/tests/             单元与集成测试
backend/alembic/           数据库迁移
config/                    自选池、策略参数、主题分类
reports/                   运行时报告（默认不入 Git）
deploy/aliyun/             阿里云 ECS 脚本
scripts/                   冒烟、备份、恢复、参考源码拉取
codex/skills/fund-research Codex 研究 Skill
vendor/                    GitHub 参考仓库清单，不参与运行
```

## 本地 Mock 启动

需要 Python 3.11+：

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'

export APP_ENV=development
export AUTH_ENABLED=false
export MARKET_PROVIDER=mock
export DATABASE_URL=sqlite:///./fund_decision.sqlite3

fund-decision bootstrap --lookback-days 420
uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
```

打开 `http://127.0.0.1:8000`。Mock 仅用于验证页面和流水线，所有信号都会被标记为不可执行。

## 阿里云 ECS 生产部署

详见 [`docs/ALIYUN_DEPLOYMENT.md`](docs/ALIYUN_DEPLOYMENT.md)。核心步骤：

```bash
sudo bash deploy/aliyun/bootstrap_host.sh
sudo mkdir -p /opt/china-fund-decision
# 将源码复制或 git clone 到上述目录
cd /opt/china-fund-decision
cp deploy/.env.production.example .env
python3 scripts/generate_secrets.py
# 将生成的值、TUSHARE_TOKEN 和模型配置写入 .env
sudo bash deploy/aliyun/deploy.sh
```

Compose 只把应用映射到 `127.0.0.1:8080`，PostgreSQL 不映射宿主机端口。公网访问应经过 Caddy/Nginx HTTPS；ECS 安全组只开放 80/443，SSH 22 仅允许可信 IP。

## 配置真实自选池

编辑 [`config/watchlist.json`](config/watchlist.json)。第一版建议控制在 30～100 只高流动性 ETF/LOF，并为每只基金明确：

- `ts_code`、名称和类型；
- 一级主题与二级主题；
- 跟踪指数；
- 是否启用。

更新后执行：

```bash
docker compose run --rm api fund-decision run-task sync_instruments
docker compose run --rm api fund-decision bootstrap --lookback-days 900
```

## 新闻源

默认使用 Tushare 可用的新闻接口。可在 `.env` 中额外配置普通 RSS/Atom 地址或自建 RSSHub 路由：

```env
NEWS_RSS_URLS=https://your-rsshub.example/route-a,https://publisher.example/feed.xml
```

系统会聚合、去重并分别记录各新闻源的成功、空结果或失败。不要在 RSS URL 中写入会出现在日志里的长期凭据。

## 命令

```bash
fund-decision run-task sync_instruments
fund-decision run-task refresh_bars --lookback-days 900
fund-decision run-task refresh_quotes
fund-decision run-task refresh_news
fund-decision run-task refresh_indicators
fund-decision run-task refresh_forecasts
fund-decision run-task refresh_signals
fund-decision run-task validate_forecasts
fund-decision run-task backtest_rotation
fund-decision run-task generate_report
fund-decision bootstrap --lookback-days 900
```

## 当前边界

尚未声称完成的内容包括：

- 你的 Tushare 账号接口权限和真实服务器出口网络验证；
- 真实 ETF/LOF 池的主题纯度、规模、费率和跟踪误差补齐；
- 真实市场约束下的回测复核：停牌、涨跌停无法成交、LOF 溢价、现金收益与独立第二引擎对账；
- 预测概率校准和模型封版；
- 阿里云实例上的 Docker 构建、域名证书、告警和恢复演练；
- 自动交易。

这些任务已写入 [`CODEX_DEPLOYMENT_TASKS.md`](CODEX_DEPLOYMENT_TASKS.md)。

## 安全与许可证

个人私用并不会自动取消第三方许可证、署名要求、保密义务或服务条款。参考源码采用隔离的浅克隆方式；生产应用不从 `vendor/src` 导入代码。个人研究源码可用 `./scripts/fetch_reference_sources.sh --include-personal-use` 显式下载到隔离目录，但该开关不免除上游条款。严禁把 GitHub 中发现的 Token、内网地址、账户 ID 或历史数据复制到本项目。

本仓库自有代码按 MIT License 提供；第三方说明见 [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md)。
