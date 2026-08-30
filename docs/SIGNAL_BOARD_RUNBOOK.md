# 截图同款信号板运行手册

## 目标

在不改变确定性指标、预测和生产信号边界的前提下，将首页改造成任务截图的信息结构：彩色汇总、红色盘中总结、市场锚、31行业选择器、五级信号组、明日预测和底部证据卡。

## 本地启动

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e '.[dev]'

export APP_ENV=development
export AUTH_ENABLED=false
export MARKET_PROVIDER=mock
export DATABASE_URL=sqlite:///./signal_board_dev.sqlite3
fund-decision bootstrap --lookback-days 520
uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
```

打开 `http://127.0.0.1:8000`，检查首页顶部是否出现“ETF 信号分级与明日预测”。

## 自动验证

```bash
pytest -q
python -m compileall -q backend/app
node --check backend/app/static/app.js
node --check backend/app/static/screenshot_signal_board.js
python codex/skills/fund-research/scripts/check_no_secrets.py
```

迁移验证：

```bash
export APP_ENV=test AUTH_ENABLED=false MARKET_PROVIDER=mock AUTO_CREATE_SCHEMA=false
export PRIVATE_ACCESS_TOKEN=CHANGE_ME_SIGNAL_BOARD_TEST_TOKEN
export DATABASE_URL=sqlite:////tmp/signal-board-migration.sqlite3
rm -f /tmp/signal-board-migration.sqlite3
alembic upgrade head
alembic downgrade b3c4d5e6f7a8
alembic upgrade head
```

API 验证：

```bash
curl http://127.0.0.1:8000/api/industry-board
curl http://127.0.0.1:8000/api/signal-board
```

生产启用认证时必须通过 `Authorization: Bearer ...` 请求，禁止把 Token 放入 URL。

## 人工视觉验收

至少检查 1440、1280、1024 和 390 像素宽度：

- 红涨绿跌是否一致；
- 汇总卡和信号徽标是否有明确颜色；
- 五级分组是否均有标题、数量和空状态；
- 13列在桌面端可横向滚动且不相互覆盖；
- 明日预测显示收益、`conf` 和校准状态；
- QDII代理警告始终可见；
- 点击行业标签只筛选对应行业；
- 未映射行业不可误点成有行情的基金；
- 点击原有刷新按钮后信号板也刷新；
- 原有持仓、新闻、信号中心和系统页仍可使用。

## 真实环境卡点

远端CI只能验证Mock、代码、迁移、Compose和镜像，不能完成：

1. Tushare Token权限；
2. AKShare在阿里云ECS的出口稳定性；
3. 行业ETF代码、跟踪指数、规模和流动性资格；
4. 50–150只活动自选池的最终选择；
5. 至少五年真实历史数据；
6. 实时行情源时间戳；
7. 真实PostgreSQL备份恢复；
8. 预测walk-forward和Holdout校准；
9. 真实浏览器截图与公司任务图片逐项比对。

这些工作未完成时保持：

```text
qualification_status=pending_real_provider_qualification
calibration_status=not_calibrated
actionable=false  # 实时时间戳未认证时
```

## 加入真实活动自选池

`config/industry_board.json` 是展示和研究注册表，不会自动写入 `config/watchlist.json`。本地Agent需要先验证基金，再人工选择是否加入活动池。修改后执行：

```bash
fund-decision run-task sync_instruments
fund-decision run-task refresh_bars --lookback-days 2200
fund-decision run-task refresh_indicators
fund-decision run-task refresh_forecasts
fund-decision run-task refresh_quotes
fund-decision run-task refresh_signals
```

## 回滚

本功能在独立分支开发。回滚方式是切回 `main`；不要在生产数据库手工删除字段。本分支未新增数据库迁移。
