# 本地 Codex 执行 Prompt（v0.7.0）

将本文件全文作为本地 Codex 的首轮任务说明。执行前必须先阅读仓库根目录 `AGENTS.md`。

---

你现在接手中国 ETF/LOF 私有研究系统：

- Repository: `https://github.com/Jovifei/ETF-Fund-Analysis`
- 目标发行版：`0.7.0`
- 预期组件版本：
  - `signal-v0.7.0-research`
  - `indicator-v0.5.1`
  - `similarity-corridor-v0.7.0`
  - `feature-store-v0.7.0`
- 部署目标：阿里云 Linux ECS
- 使用性质：用户个人私有研究
- 严禁自动下单、券商连接、密钥回显、Mock 冒充真实数据、未来数据泄漏和自动调参追逐单次回测。

## 1. 项目目的

系统用于中国场内 ETF/LOF 的行情、技术指标、新闻、主题轮动、持仓和多期限概率研究。它需要输出：

- 当前机会/风险/止盈研究状态；
- 1、5、20 个交易日上涨概率和预期收益；
- 终点收盘价格区间；
- 未来路径可能支撑区和压力区；
- 支撑/压力触及概率；
- 当前价格位于预测走廊的位置；
- 预测样本数、区间方法、数据截止、模型/特征/配置/Git 版本；
- 因子 IC、Rank IC、ICIR、分位收益、换手、主题和市场状态稳定性；
- 结合实际持仓成本和目标仓位的研究提示。

硬指标、预测数值、仓位、回测和风险计算只能由确定性 Python 完成。LLM 只能做新闻事实抽取、事件分类、主题映射和只读解释。

## 2. 仓库已经完成的代码

当前代码应包含：

1. FastAPI、PostgreSQL、Alembic、Docker Compose、Scheduler、SSE、数据库账户和可撤销浏览器会话认证（旧 Bearer 仅限非生产迁移/测试兼容）；
2. Tushare 主源、AKShare 备用、Composite Provider、RSS/Atom 新闻；
3. MA、MACD、KDJ、RSI、ATR、BOLL、TD、量比；
4. OBV、MFI、CMF、ADX/DMI、CCI、WR、ROC、RSRS、RPS；
5. 箱体、海龟突破、放量突破、缩量回踩、假突破、成交密集成本分布近似；
6. 高级统一 Feature Store；
7. 1/5/20 日相似样本基线；
8. 未来终点收益、未来路径最低/最高收益标签；
9. 终点收盘区间、路径低点/高点区间、走廊位置、支撑/压力触及概率；
10. 研究级局部残差区间扩张，明确不等同于已校准 MAPIE；
11. walk-forward 验证：方向准确率、Brier、MAE、pinball loss、80/90% coverage、区间宽度、quantile crossing、路径区间覆盖、触及概率 Brier；
12. Alphalens 风格因子分析任务；
13. 可选 LightGBM/CatBoost 全局模型研究任务；
14. exchange_calendars XSHG 统一交易日历；
15. 上游行情 source timestamp 与 fetched_at 分离，时间戳未验证时 fail-closed；
16. 指标和预测快照保存 Git SHA、配置哈希和特征 Schema；
17. 事件驱动轮动回测、策略消融、持仓、新闻、多模型只读审阅、市场背景和 OCR；
18. 页面显示价格走廊，且信号分、走廊位置和预测置信度是三个不同概念。

这些代码完成不等于真实环境资格通过。预测默认继续是 `not_calibrated`。

## 3. 第一阶段：确认源码和自动门禁

执行：

```bash
git status --short
git branch --show-current
git log -5 --oneline
git pull --ff-only origin main
grep '^version' pyproject.toml
cat config/strategy.json | python -m json.tool >/dev/null
```

预期版本为 `0.7.0`。不要自动 reset、clean 或删除用户文件。

阅读：

```text
AGENTS.md
STATUS.md
HANDOFF.md
VALIDATION.md
LOCAL_CODEX_HANDOFF_V070.md
docs/ROADMAP_V070.md
docs/LOCAL_AGENT_PROMPT_V070.md
CODEX_DEPLOYMENT_TASKS.md
```

运行：

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e '.[dev]'
pytest -q
python -m compileall -q backend/app
node --check backend/app/static/app.js
python codex/skills/fund-research/scripts/check_no_secrets.py
```

再用临时 SQLite 检查迁移：

```bash
export APP_ENV=test AUTH_ENABLED=false MARKET_PROVIDER=mock AUTO_CREATE_SCHEMA=false
export DATABASE_URL=sqlite:////tmp/etf-v070-migration.sqlite3
rm -f /tmp/etf-v070-migration.sqlite3
alembic upgrade head
alembic downgrade b3c4d5e6f7a8
alembic upgrade head
```

失败时先写复现测试，不得删除测试、放宽安全门或改变阈值让结果好看。

## 4. 第二阶段：只在本机/ECS配置真实环境

复制配置：

```bash
cp deploy/.env.production.example .env
python scripts/generate_secrets.py
chmod 600 .env
```

人工填写但不要回显：

- `POSTGRES_PASSWORD`
- `TUSHARE_TOKEN`
- OpenAI-compatible 模型配置
- 可选新闻 RSS URL

必须保持：

```env
APP_ENV=production
AUTH_ENABLED=true
DATABASE_URL=postgresql+psycopg://<compose-managed-postgres-url>
AUTO_CREATE_SCHEMA=false
AUTH_COOKIE_SECURE=true
MARKET_PROVIDER=composite
ALLOW_MOCK_FALLBACK=false
SCHEDULER_ENABLED=false
ANALYSIS_ENABLED=false
```

浏览器登录使用迁移后由 `fund-decision auth-bootstrap-admin` 创建的数据库账户；密码哈希与会话只保存在数据库，不在浏览器保存密码或会话令牌。生产不得配置 `AUTH_USERNAME`、`AUTH_EMAIL`、`AUTH_PASSWORD_HASH`、`AUTH_SESSION_SECRET` 或旧 Bearer 凭据。

初次数据资格完成前不要启动 scheduler 或分析模型。

## 5. 数据源能力矩阵

运行安全、脱敏的 Provider 检查。只报告“已配置/未配置”，绝不输出 Token。

至少验证：

- Tushare `fund_basic`；
- `fund_daily`；
- `trade_cal`；
- 每个实时候选接口；
- 上游真实行情时间戳；
- 新闻接口；
- AKShare ETF 列表、日线、实时行情、新闻；
- 阿里云出口延迟、错误率、限频和连续稳定性。

对于每个接口记录：

```text
provider
operation
status
record_count
latency_ms
field_names
source_timestamp_available
timestamp_verified
error_class
```

禁止保存原始异常中可能含有的 Token、URL 参数或 Cookie。

任何实时记录必须同时满足：

- 上游提供真实源时间；
- 日期为当日；
- 时间位于合法交易会话；
- 与抓取时间差在阈值内；
- 代码、价格、昨收、成交量和成交额一致；
- Provider 资格已经人工确认。

否则必须保持 `timestamp_verified=false`、`is_realtime=false` 和 `actionable=false`。

## 6. 建立真实 ETF/LOF 池

当前演示池不能作为正式选基池。建立 50–150 只高流动性 ETF/LOF，覆盖：

- 宽基、大小盘、红利和价值；
- 科技、AI、半导体、通信、计算机、机器人；
- 医药、创新药、消费、白酒；
- 新能源、电池、光伏、汽车；
- 黄金、有色、煤炭、石油；
- 银行、证券、保险、地产、基建；
- 军工、农业、传媒等。

每项至少维护：

```text
ts_code
symbol
name
kind
exchange
theme_l1
theme_l2
benchmark
enabled
```

可取得时补充：规模、日均成交额、买卖价差、跟踪误差、管理费、成立日期、溢价率和主题纯度。不要一次纳入全部基金。

## 7. 拉取真实历史并抽检

目标至少 5 年日线，理想为 8 年。先同步和 bootstrap：

```bash
fund-decision run-task sync_instruments
fund-decision bootstrap --lookback-days 2200
```

随机选择至少 10 只基金，与另一个可靠来源逐日核对：

- OHLC；
- 成交量/成交额单位；
- 复权；
- 停牌和缺口；
- 分红、拆分和异常跳空；
- 代码与交易日期；
- LOF 溢价字段。

差异只能在 Provider Adapter 解决，不得在信号或模型层猜测。

## 8. 跑真实预测、走廊和因子验证

顺序：

```bash
fund-decision run-task refresh_bars --lookback-days 2200
fund-decision run-task refresh_indicators
fund-decision run-task refresh_forecasts
fund-decision run-task validate_forecasts
fund-decision run-task analyze_factors
fund-decision run-task backtest_rotation
fund-decision run-task backtest_ablation
```

重点检查：

- 1、5、20 日分别评估；
- 终点收益和路径低/高标签无未来泄漏；
- q10 <= q50 <= q90；
- 80%/90% coverage 与区间宽度之间的权衡；
- path low/high 区间覆盖；
- 支撑/压力触及概率 Brier；
- 模型对不同市场状态、主题和年份的稳定性；
- `full` 是否真的击败相似样本/动量基线；
- 哪些指标只增加换手而没有增量收益；
- 哪些指标降低回撤但不提升收益；
- IC、Rank IC、ICIR 和分位收益是否跨窗口稳定。

保留最近 6–12 个月完全不参与调参，作为 Holdout。禁止随机打乱时间序列。

## 9. 可选研究依赖

核心系统无需这些依赖即可运行。隔离研究环境安装：

```bash
pip install -e '.[research]'
python scripts/research_capability_smoke.py
fund-decision run-task research_capabilities
fund-decision run-task research_global_models
```

逐项完成：

- 使用 `alphalens-reloaded` 对内建因子报告做第二实现对账；
- 使用 MAPIE 对终点和路径区间做真正的时间序列 conformal 校准；
- 使用 MLForecast 训练跨 ETF 全局模型；
- 使用 LightGBM/CatBoost 分位数模型与相似样本基线比较；
- 使用 AKQuant 做独立事件驱动回测；
- 视需要使用 RQAlpha 核对中国市场撮合和费用；
- 使用 Qlib 作为离线实验与模型注册框架；
- 使用 Riskfolio 研究 HRP、风险预算、CVaR 和换手约束。

这些工具只能读经过清洗的研究快照，不能直接修改生产策略或数据库。

## 10. PostgreSQL、Docker 和阿里云验收

```bash
sudo bash deploy/aliyun/bootstrap_host.sh
docker compose build --pull
docker compose up -d db api
docker compose run --rm api alembic upgrade head
docker compose ps
docker compose logs --tail=200 api
curl http://127.0.0.1:8080/api/health
```

完成：

- PostgreSQL 16 真实迁移；
- 升级、降级和再次升级；
- 备份 SHA-256；
- 隔离数据库恢复；
- API 只绑定 `127.0.0.1:8080`；
- PostgreSQL 不映射公网；
- Caddy/Nginx HTTPS；
- ECS 安全组只开放必要端口。

## 11. Scheduler 影子运行

数据资格通过后才启用：

```bash
docker compose up -d scheduler
docker compose logs -f --tail=200 scheduler
```

观察至少 20 个真实交易日：

- 行情约每 3 分钟；
- 信号每 10–15 分钟；
- 午休不生成新价格信号；
- 新闻午间约每 10 分钟、其他约每 30 分钟；
- 收盘任务只运行一次；
- XSHG 日历在节假日正确停机；
- 上游时间戳陈旧时操作级信号自动关闭；
- SSE 页面增量更新；
- Provider audit、任务失败和恢复完整留痕。

## 12. 晋升规则

在以下条件全部满足前不得把预测改为 `calibrated`：

1. 真实数据源和时间戳资格通过；
2. 真实 ETF 池至少五年数据；
3. rolling-origin 与完全隔离 Holdout 完成；
4. 区间 coverage、宽度和 pinball 指标达标；
5. 相比相似样本基线有稳定增量；
6. AKQuant/RQAlpha 等第二引擎差异可解释；
7. 20 个交易日影子运行无严重问题；
8. 用户人工批准模型、特征、阈值和版本。

## 13. 输出报告

创建：

```text
deployment_reports/YYYY-MM-DD-v070-real-qualification.md
```

报告包含：

- Git commit 和版本；
- OS/Python/Docker/PostgreSQL 版本；
- 测试和迁移；
- Provider 能力矩阵；
- watchlist 数量与覆盖；
- 历史数据范围和异常；
- 预测与走廊指标；
- 因子有效性；
- 回测与第二引擎差异；
- 影子运行状态；
- 尚未完成事项；
- 回滚点。

不得包含 Token、密码、Cookie、账户号、公网 IP、原始持仓截图或长期签名 URL。

完成真实资格验证后先向用户汇报，不要自动晋升模型、修改阈值或开启任何交易接口。
