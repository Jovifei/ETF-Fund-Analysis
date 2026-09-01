# v0.7.0 资格验证交接文档

更新时间：2026-08-30
分支：`main` @ `121f70f`（接续提交含 Phase B 收尾）
状态：**Phase A + Phase B（本地基线）完成；Phase C 部分（Alembic 演练）；本地 Docker 看板可进；ETF 信号分级页已落地（Mock）；Phase D+ 阻塞 TUSHARE_TOKEN / ECS**

---

## 一、已完成（Phase 0 + Phase A，2026-08-29/30）

### Phase 0 — 同步接管

| 项 | 状态 |
|---|---|
| main 快进到 v0.7.0（`7223069`） | ✅ |
| pyproject 0.7.0；strategy.json = signal-v0.7.0-research / indicator-v0.5.1 / similarity-corridor-v0.7.0 / rotation-v0.5.1 / feature-store-v0.7.0 | ✅（与任务书命名差异已记录：signal 加 `-research` 后缀，indicator/rotation 为 0.5.1） |
| 文档通读（HANDOFF_V070/RELEASE_V070/ROADMAP_V070/VALIDATION/ARCHITECTURE/5 个 config） | ✅ |
| Python 3.12 venv + `.[dev,market]` 安装 | ✅ |
| 基线门禁 | ✅ 337 通过 + 2 跳过，compileall/node/secret-scan 全绿 |

### Phase A — 差距补齐开发（8 个功能 + 2 配置 + 2 文档）

| 任务 | Commit | 内容 | 测试 |
|---|---|---|---|
| A1 | `c16c1a4` + `8b6ceec` | `scripts/qualify_postgres.sh`——隔离 PG16 演练（9 步：起容器→迁移 up→down→up→种子→备份→SHA-256→清库→恢复→完整性核对），零密码泄漏（bash -x 审计验证），拒绝生产库名 | 真实运行 exit 0，12.8s，head `d5e6f7a8b9c0` |
| A2 | `d114fad` | `scripts/qualify_market_data.py`——Provider 能力矩阵（Tushare/AKShare/Composite 各接口权限、限频、延迟、单位），严格区分 source_timestamp/fetched_at/verification_status/is_realtime/degraded_reason，8 条 actionable 门槛全过才 true | mock exit 0（3 条全 false）、tushare 无 token exit 3、默认拒绝 mock exit 3、密钥扫描干净 |
| A3 | `c0c3cfc` | `scripts/build_etf_universe.py`——真实 ETF/LOF 池构建（dry-run 产候选 JSON：规模/费率/上市年限/流动性/退市风险/主题分类；`--write-watchlist` 必须同时给 `--confirm-private-use`；强制保留 510300.SH 门控基准） | token 缺失 exit 3、分类断言 9 项全绿 |
| A4 | `d6765c5` | **calibrate_forecasts 任务** + CalibrationProfile 表（迁移 `d5e6f7a8b9c0`）——从 validate_forecasts 报告创建候选 Profile（幂等），批准前核对模型版本/schema/config_hash/门槛样本覆盖率/Holdout，**绝不自动改 calibration_status** | 6 测试（skip/幂等/拒绝/门槛拦截/版本拦截） |
| A5 | `90a640e` | **optimize_portfolio 任务**——等权/得分倾斜/风险预算（反波动率）三策略，单基金/单主题/总暴露/换手约束，**只输出研究 JSON，不写 Holding** | 3 测试（任务存在/三策略+约束/Mock 标记） |
| A6 | `d4e9fed` | **backtest_crosscheck 任务**——独立第二引擎：读主引擎报告 → 用原始 DailyBar 独立重放 → 对账权益/交易/费用；差异超阈值即 FAIL | 3 测试（任务存在/对账判定/Mock 标记） |
| A7 | `79df048` | **shadow_run_audit 任务**——每日对比已发布预测 vs 实际（区间覆盖/方向正确/支撑压力触及/信号状态），**不修改预测、不补写历史** | 3 测试（任务存在/报告产出/不变式验证） |
| A8 | `76892b6` | config/integration_registry.json（10 个集成资格）+ config/universe_theme_rules.json（20 条主题规则）+ docs/FORECAST_CORRIDOR.md + docs/RESEARCH_INTEGRATIONS.md | — |

### 最终门禁（A9）

- `pytest`：**352 通过 + 2 跳过**（基线 337 + 新增 15）
- `compileall`：✅；`node --check`：✅；`check_no_secrets.py .`：✅；`bash -n` 全部脚本：✅
- Alembic 迁移链：`158ca7025305 → … → c4d5e6f7a8b9 → d5e6f7a8b9c0 (head)`，升级→降级→升级全链路通过

## 二、任务注册表现状

TaskService 现有 **22 个任务**（原 18 + calibrate_forecasts + optimize_portfolio + backtest_crosscheck + shadow_run_audit）。运行 `fund-decision run-task <name>` 或 `POST /api/tasks/<name>` 可调用。

## 三、下一步（Phase B → Q）

### Phase B — 本地基线报告 ✅（2026-08-30）

- 报告：`deployment_reports/2026-08-30-local-validation.md`
- 生产资格摘要：`deployment_reports/2026-08-30-production-qualification.md`
- Mock 研究任务烟测全部 exit 0（含 analyze_factors，修复 `refresh_daily_bars` 回填后）
- `qualify_postgres.sh` head 修订为 `d5e6f7a8b9c0`；Windows 上 Alembic up/down/up 手动通过；完整九步备份恢复待在 Linux ECS 执行

### Phase C — PostgreSQL 资格（部分）

```bash
bash scripts/qualify_postgres.sh --json deployment_reports/pg-qualification.json
```

Windows 无 bash 时已在 Docker PG16 上验证 Alembic 链；完整 pg_dump/restore 见 ECS。

### Phase D — Provider 能力矩阵 ⚠️ **需要用户配置 TUSHARE_TOKEN**

用户操作：本机 `.env`（或环境变量）写入 `TUSHARE_TOKEN=<真实值>`，**不要发到聊天**。

确认状态（我只报告 configured/missing）：
```bash
.venv/Scripts/python.exe scripts/qualify_market_data.py --provider composite \
  --sample-size 10 --history-years 5 --output deployment_reports/provider-qualification.json
```

产出：Tushare 各接口权限/限频/延迟、AKShare 出口稳定性、Composite 主备命中、每条行情的 actionable 判定。

### Phase E — 真实 ETF/LOF 池 ⚠️ **需要用户人工审阅**

```bash
# dry-run（只产候选 JSON，不动 watchlist）
.venv/Scripts/python.exe scripts/build_etf_universe.py \
  --target-size 100 --history-years 5 --output deployment_reports/watchlist-candidate.json
```

用户审阅候选池（主题覆盖、规模、流动性、停牌/退市）后：
```bash
.venv/Scripts/python.exe scripts/build_etf_universe.py --target-size 100 \
  --history-years 5 --write-watchlist --confirm-private-use
```

### Phase F — 真实历史数据（需 Phase D/E 通过）

```bash
fund-decision run-task sync_instruments
fund-decision run-task refresh_bars --lookback-days 2200
fund-decision run-task refresh_indicators
fund-decision run-task refresh_forecasts
fund-decision run-task refresh_signals
```

质量检查：OHLC 关系/重复日/未来日期/成交量额单位/复权；**抽 10 只 ETF × 最近 60 交易日双源核对**。

### Phase G — 预测走廊验证与校准 ⚠️ **需要用户签字批准**

```bash
fund-decision run-task validate_forecasts
fund-decision run-task calibrate_forecasts   # 只产候选
```

用户核对（模型版本/schema/config_hash/样本/覆盖率/Holdout）后，通过 API 显式批准或拒绝。

### Phase H — 因子有效性

```bash
fund-decision run-task analyze_factors
```

无增量价值的因子给降权/移除提案，**用户批准才改配置**。

### Phase I — 全局模型（可选）

```bash
pip install -e '.[research]'
fund-decision run-task research_global_models
```

与 similarity-corridor-v0.7.0 比较；不稳定胜出不批准。

### Phase J — 回测与消融

```bash
fund-decision run-task backtest_rotation
fund-decision run-task backtest_ablation
fund-decision run-task backtest_crosscheck
```

核对 `decision_at=close_t`、`execution_at=open_t_plus_1`、`future_data_in_features=false`。

### Phase K — 组合研究

```bash
fund-decision run-task optimize_portfolio
```

只产研究建议，不写持仓。

### Phase L — 新闻

```bash
fund-decision run-task refresh_news
fund-decision run-task analyze_news
```

### Phase M — 集成资格

```bash
fund-decision run-task research_capabilities
```

### Phase N+O — ECS 部署 + 20 交易日影子运行

按 `docs/ALIYUN_DEPLOYMENT.md` 与 `deploy/aliyun/`；scheduler 先关，**≥20 个真实交易日**每日 `run-task shadow_run_audit`；期间不下单/不自动调参/不删失败记录/不补写历史。

### Phase P — 启用 scheduler

影子达标后 `docker compose up -d scheduler`，观察完整交易日。

### Phase Q — 最终报告

`deployment_reports/YYYY-MM-DD-production-qualification.md`——commit/版本/OS/测试/迁移/Provider 矩阵/池规模/10 只核对/实时资格/预测验证/因子验证/消融/第二引擎对账/组合/影子状态/未完成项/回滚点。不含 Token/密码/账户号/公网 IP/持仓截图。

## 本地看板与账户认证（2026-09-01）

- Docker：`docker compose up -d db api`，浏览器 `http://127.0.0.1:8080/`。登录框填写 `AUTH_USERNAME` 或可选 `AUTH_EMAIL` 与原始密码；服务器 `.env` 只保存 `AUTH_PASSWORD_HASH`（本地 `scripts/generate_password_hash.py` 生成）和 `AUTH_SESSION_SECRET`。本机 HTTP 模板使用 `APP_ENV=development` 与 `AUTH_COOKIE_SECURE=false`；生产 HTTPS 必须使用 `AUTH_COOKIE_SECURE=true`。
- `PRIVATE_ACCESS_TOKEN` 是可选旧 Bearer CLI/API 凭据，不能用于浏览器登录。当前版本没有 SMTP 或邮件 OTP，邮箱只是同一账户的别名。
- 页签：决策看板 | 信号中心 | **ETF信号分级** | 持仓 | 新闻事件 | 系统。分级页是研究复刻，不是下单。
- 演示/行业池已写入 `config/watchlist.json`（含行业 ETF、标普500、纳斯达克、黄金）。无 `TUSHARE_TOKEN` 时走 Mock，分级可渲染但 `actionable=false`。
- **下一步 Token**：本机 `.env` 写入 `TUSHARE_TOKEN`（不要发到聊天）→ 跑 Provider 矩阵与 `fund_basic` 核对停牌/清盘替换 → 再 bootstrap 真实日线。scheduler 仍等资格，不要提前开。

## 四、需要用户配合的时点汇总

| 时点 | 用户做什么 | 我做什么 |
|---|---|---|
| Phase D 前 | 本机 `.env` 写 `TUSHARE_TOKEN` | 报 configured/missing，跑 Provider 矩阵 |
| Phase E | 审阅候选池 → 确认 | dry-run + 审阅报告 |
| Phase G/H/I | 校准/因子/模型批准 | 候选生成 + 核对单 |

## 五、边界与承诺

- **不自动交易**；不连券商；不下单；不自动修改持仓
- 预测永远 `not_calibrated` 直至人工批准
- 因子无增量价值 → 降权或删除（用户批准）
- 数据不足 → 停止信号
- 无法验证 → 如实标记未验证
- **不制造确定性**
