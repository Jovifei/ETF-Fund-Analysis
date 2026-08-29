# 本地基线验证报告

生成时间：2026-08-30（Asia/Shanghai）  
Git commit：`121f70fe91a10f83bf5a885b097f03b268ceed88`（接续提交前基线）  
分支：`feat/v070-qualification`（与 `origin/main` 同 commit）  
环境：Windows 10，Python 3.12.10（`.venv`），Docker 29.7.2，Compose v5.4.0

## 一、源码状态

| 检查项 | 结果 |
|---|---|
| 工作分支 | `feat/v070-qualification`（HEAD 与 `origin/main` 一致） |
| 脏工作区 | 仅 `.zcode/` 未跟踪；未执行 reset/clean/stash |
| `pyproject.toml` 版本 | `0.7.0` |
| `config/strategy.json` | `signal-v0.7.0-research` / `indicator-v0.5.1` / `similarity-corridor-v0.7.0` / `rotation-v0.5.1` / `feature-store-v0.7.0`（与任务书命名差异已记录） |

## 二、密钥状态（仅 configured/missing）

| 变量 | 状态 |
|---|---|
| TUSHARE_TOKEN | **missing**（无 `.env`，环境变量未设置） |
| OPENAI_API_KEY | **missing** |

## 三、命令与退出码

| 命令 | 退出码 | 结果摘要 |
|---|---|---|
| `pytest -q` | 0 | 全绿；2 项跳过（与基线一致）；警告：`StarletteDeprecationWarning`（httpx2）、`exchange_calendars` NumPy timedelta、`sqlite3` datetime adapter |
| `python -m compileall -q backend/app` | 0 | 通过 |
| `node --check backend/app/static/app.js` | 0 | 通过 |
| `python codex/skills/fund-research/scripts/check_no_secrets.py .` | 0 | `no obvious committed secrets found` |
| `bash -n scripts/*.sh deploy/aliyun/*.sh`（Alpine 容器） | 部分 | `backup_postgres.sh`、`qualify_postgres.sh`、`restore_postgres.sh`、`smoke_http.sh`、`deploy/aliyun/*.sh` 通过；`fetch_reference_sources.sh` 原为 CRLF，已在本轮修复为 LF |
| `shellcheck` | 未执行 | 本机未安装 `shellcheck` |
| `docker compose config` | 未通过 | 缺少 `.env`（`env file .env not found`）；需在 ECS 按 `deploy/.env.production.example` 生成后重试 |
| `scripts/provider_smoke.py` | 0 | Mock provider；`tushare_token_present=false`；quotes 全部 degraded |
| `scripts/qualify_market_data.py`（默认） | 3 | 预期：`mock_refused`（Mock 不能作为资格证据） |
| `scripts/qualify_market_data.py --allow-mock-check` | 0 | 结构检查 JSON → `deployment_reports/provider-qualification-mock-structure.json`；3 条行情 `actionable_count=0` |
| `scripts/build_etf_universe.py`（dry-run） | 3 | 预期：`token_missing` |
| `scripts/qualify_postgres.sh`（WSL/Git Bash） | 未完整 | Windows 无可用 bash；改用 PowerShell + Docker 分步验证（见生产资格报告） |

## 四、Mock/SQLite 研究任务烟测（`fund-decision run-task`）

在清除 `DATABASE_URL`、默认 SQLite、`MARKET_PROVIDER=mock` 下执行：

| 任务 | 退出码 | 备注 |
|---|---|---|
| `bootstrap --lookback-days 900` | 0 | 生成 Mock 管道数据 |
| `validate_forecasts` | 0 | 9 只 instrument |
| `calibrate_forecasts` | 0 | 候选 Profile；未批准 |
| `backtest_rotation` | 0 | 8 decisions |
| `backtest_ablation` | 0 | 多份 rotation 报告 |
| `backtest_crosscheck` | 0 | 第二引擎对账报告 |
| `optimize_portfolio` | 0 | 研究 JSON；不写 Holding |
| `analyze_factors` | 0 | 修复 `refresh_bars` 回填逻辑后通过；30 factors × 9 instruments |
| `research_capabilities` | 0 | 集成矩阵 |
| `shadow_run_audit` | 0 | 影子审计报告（Mock 数据） |

## 五、本轮代码修复

1. **`scripts/qualify_postgres.sh`**：`EXPECTED_HEAD` 更新为 `d5e6f7a8b9c0`，`DOWNGRADE_REV` 为 `c4d5e6f7a8b9`（与 A4 迁移一致）。
2. **`backend/app/services/market_service.py`**：`refresh_daily_bars` 在已有部分历史时仍可向更早日期回填（满足 `--lookback-days 2200` 语义）。
3. **`scripts/fetch_reference_sources.sh`**：CRLF → LF，`bash -n` 可通过。

## 六、未完成（需用户 / ECS）

- 真实 Tushare/AKShare Provider 能力矩阵（需 `TUSHARE_TOKEN`）
- 真实 ETF/LOF 池 dry-run 与人工审阅
- 完整 `qualify_postgres.sh` 九步备份恢复演练（建议在 Linux ECS 执行）
- Docker Compose 生产镜像构建与 HTTPS 部署
- 20 交易日影子运行
