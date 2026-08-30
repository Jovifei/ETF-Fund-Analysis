# 本地 Codex 接收 Prompt：截图同款行业 ETF 信号板

将本文件全文交给本地 Codex。开始前必须阅读根目录 `AGENTS.md`。

---

你现在接收项目：

- Repository: `https://github.com/Jovifei/ETF-Fund-Analysis`
- 工作分支：`feat/screenshot-signal-board-v2`
- 基线发行：`v0.7.0`
- 用途：用户个人私有的中国 ETF/LOF 研究系统
- 目标：验证截图同款彩色行业信号板，并完成只能在本地或阿里云ECS执行的真实数据资格工作

## 一、代码已经完成的内容

本分支已经实现：

1. 申万2021版31个一级行业注册表；
2. 行业ETF状态：直接ETF、主题代理、待映射；
3. 四个市场锚：沪深300、标普500ETF代理、纳指ETF代理、黄金ETF；
4. 彩色汇总卡和红色盘中总结；
5. 31行业筛选标签；
6. 五级信号组：可加仓、可入场、可试探、观望、减仓；
7. 截图列：标的、今日涨幅、较上一信号、量能、均线、MACD、KDJ、TD、RSI、板块ETF代理宽度、近1周、明日预测、建议；
8. 底部“盘中核心变化”和“明日预测”证据卡；
9. `/api/industry-board` 和 `/api/signal-board`；
10. 未进入活动池的基金只显示不可执行占位，不制造行情和预测；
11. 完整文档和Skill知识章节。

本分支没有改动生产信号权重、技术指标公式、预测模型或数据库迁移。

## 二、安全边界

禁止：

- 自动交易或接入券商；
- 打印、提交或上传 `.env`、Token、API Key、Cookie、密码、账户号、公网IP；
- 把Mock、日线退化或待资格数据称为实时；
- 把 `513500.SH` 或 `513100.SH` 称为美股指数实时点位；
- 把ETF成交密集分布称为真实筹码；
- 自动把 `not_calibrated` 改成 `calibrated`；
- 为了得到好看的回测修改参数；
- 在没有用户批准时push、合并或覆盖持仓。

只能报告凭据 `configured / missing`，不能输出真实值。

## 三、拉取与核验

```bash
git status --short
git fetch origin --prune
git checkout feat/screenshot-signal-board-v2
git pull --ff-only origin feat/screenshot-signal-board-v2
git log -5 --oneline
git diff origin/main...HEAD --stat
```

阅读：

```text
AGENTS.md
README.md
STATUS.md
HANDOFF.md
VALIDATION.md
docs/SCREENSHOT_SIGNAL_BOARD.md
docs/INDUSTRY_UNIVERSE.md
docs/SIGNAL_BOARD_RUNBOOK.md
codex/skills/fund-research/references/industry-signal-board.md
config/industry_board.json
```

## 四、本地完整门禁

使用Python 3.12：

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e '.[dev]'
pytest -q
python -m compileall -q backend/app
node --check backend/app/static/app.js
node --check backend/app/static/screenshot_signal_board.js
python codex/skills/fund-research/scripts/check_no_secrets.py
```

若有ShellCheck和Docker：

```bash
shellcheck deploy/aliyun/*.sh scripts/*.sh
cp deploy/.env.production.example .env.ci
# 不要写真实密钥；只用于docker compose config的占位验证
rm -f .env.ci
```

失败时先记录复现，不要删除测试或降低断言。

## 五、Mock浏览器验收

```bash
export APP_ENV=development
export AUTH_ENABLED=false
export MARKET_PROVIDER=mock
export DATABASE_URL=sqlite:///./signal_board_dev.sqlite3
fund-decision bootstrap --lookback-days 520
uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
```

打开首页，至少检查1440、1280、1024和390像素宽度：

- 页面有明显彩色，不是纯黑白；
- 红涨绿跌；
- 五级分组和13列与任务截图一致；
- 市场锚和31行业可见；
- 行业筛选正常；
- 未映射行业不显示伪造基金；
- `conf`、`not_calibrated` 和源时间资格可见；
- 原有信号中心、持仓、新闻、系统页正常；
- 横向滚动和移动端没有严重遮挡。

保存脱敏截图到：

```text
deployment_reports/signal-board-1440.png
deployment_reports/signal-board-390.png
```

不得截图Token、持仓隐私或浏览器密码管理器。

## 六、真实行业ETF资格

检查 `config/industry_board.json` 中每个映射基金。使用Tushare和AKShare交叉核对：

- 代码、简称、全称；
- 上市状态；
- 跟踪指数；
- 成立日期；
- 基金规模；
- 近20/60日成交额；
- 买卖价差；
- 管理费；
- 场内溢折价；
- 至少五年历史日线；
- 复权、分红和拆分；
- 实时 `source_timestamp`。

每个映射输出：

```text
industry
coverage_status
proxy_ts_code
name_match
benchmark_match
liquidity_status
history_status
realtime_timestamp_status
provider_primary
provider_secondary
qualification_result
```

未通过时不要偷偷替换，应提出候选并等待用户批准。

## 七、建立活动自选池

注册表不会自动修改 `config/watchlist.json`。资格完成后生成候选差异，但先不要写：

```text
qualified industry proxies
qualified market anchors
existing extended themes
excluded/failed products with reasons
```

用户批准后才能修改活动池。建议第一版控制50–100只，不要一次纳入全部ETF。

修改后运行：

```bash
fund-decision run-task sync_instruments
fund-decision run-task refresh_bars --lookback-days 2200
fund-decision run-task refresh_indicators
fund-decision run-task refresh_forecasts
fund-decision run-task refresh_quotes
fund-decision run-task refresh_signals
```

## 八、真实数据与预测验证

分别验证：

- 行情每3分钟调度；
- 信号10–15分钟；
- 午间不产生新价格信号；
- 新闻午间10分钟、其他时段30分钟；
- `source_timestamp` 与 `fetched_at` 分离；
- 未验证实时行情 `actionable=false`；
- 1/5/20日预测仍为 `not_calibrated`；
- 终点和路径价格走廊无未来数据泄漏；
- 明日预测表格值与详情值一致。

运行：

```bash
fund-decision run-task validate_forecasts
fund-decision run-task analyze_factors
fund-decision run-task backtest_rotation
fund-decision run-task backtest_ablation
```

## 九、阿里云ECS

先保持：

```env
MARKET_PROVIDER=composite
ALLOW_MOCK_FALLBACK=false
SCHEDULER_ENABLED=false
ANALYSIS_ENABLED=false
```

完成PostgreSQL备份、迁移、恢复演练以及Provider资格后，才启动scheduler。公网只经Caddy/Nginx HTTPS，API保持绑定`127.0.0.1:8080`，PostgreSQL不暴露公网。

## 十、交付报告

创建：

```text
deployment_reports/YYYY-MM-DD-screenshot-signal-board-local.md
```

报告包括：

- 分支和提交SHA；
- 测试、JS、迁移、镜像结果；
- 浏览器尺寸和视觉差异；
- 31行业映射资格矩阵；
- 市场锚资格；
- 活动池候选；
- 实时源时间资格；
- 预测和信号一致性；
- 当前阻塞项；
- 建议修改，但不要自动push。

完成后停止，先向用户汇报并等待是否合并到main。
