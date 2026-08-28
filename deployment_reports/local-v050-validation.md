# ETF/LOF 研究系统 v0.5.0 本地验证报告

日期：2026-08-28（Asia/Shanghai）
结论：**PARTIAL / NOT READY FOR REAL STRATEGY SEALING OR PRODUCTION PROVIDER CLAIMS**

本报告只覆盖当前本地、隔离运行和已保存的 sanitized 证据。它不是实时行情、生产部署、真实策略封版或投资建议。

## 1. 执行结论与证据状态

| 状态 | 含义 |
|---|---|
| `CONFIRMED LOCAL` | 当前本地源码或隔离运行中直接观察到 |
| `MOCK_ONLY` | 仅来自 Mock 数据/Mock 引擎，不能外推为真实数据或真实绩效 |
| `PARTIAL` | 仅部分路径、字段或单次运行成立 |
| `BLOCKED` | 前置条件缺失，无法继续得出该结论 |
| `UNVERIFIED` | 有返回或代码路径，但没有足够证据确认其语义/稳定性 |

核心结论：HEAD 提交对象是 v0.5 提交，但实际 owner-dirty working tree 的有效运行时仍为 v0.4。v0.5 指标/轮动模块只有直接 dormant 证据；Provider 实际稳定性、真实历史、真实指标、策略封版和生产 Provider 声明均未建立。

## 2. 范围与安全边界

- `CONFIRMED LOCAL`：这是个人私有研究系统；不连接券商、不自动下单、不修改生产数据库、不读取或输出密钥/Token/Cookie/密码/账户标识、public IP 或 signed URL，不 push/commit。
- 当前轮明确的 repo 文件范围是：`backend/tests/conftest.py`（测试 fixture 修复）、`tasks/todo.md`（任务账本）、`deployment_reports/local-v050-validation.md`（本报告）。本报告作者不对 owner work attribution 作推断。
- 16 条实质性 pre-existing owner dirty 路径全部保留，不归因于本报告作者：`.gitignore`、`README.md`、`STATUS.md`、`THIRD_PARTY_NOTICES.md`、`VALIDATION.md`、`backend/app/core/config.py`、`backend/app/services/indicator_service.py`、`backend/app/services/task_service.py`、`backend/tests/test_backtest.py`、`backend/tests/test_indicators.py`、`backend/tests/test_pipeline.py`、`config/strategy.json`、`deploy/.env.production.example`、`docs/GITHUB_RESEARCH.md`、`pyproject.toml`、`vendor/manifest.json`。
- 外部 Provider 输出按不可信输入处理；Mock、测试、候选报告和本地通过都不能升级为真实 Provider、ECS、生产或投资结论。

## 3. 环境、Git 与版本边界

| 项目 | 观察 | 状态 |
|---|---|---|
| HEAD commit object | `ae755dfd89549abeaf772ac8c34152e80391210d`，`feat: add v0.5.0 indicator and strategy engine` | `CONFIRMED LOCAL`（不表示工作树干净） |
| 分支 | `main`，tracking `origin/main` | `CONFIRMED LOCAL` |
| 工作树 | 存在并保留 owner dirty 内容；不能称为 clean working tree | `CONFIRMED LOCAL` |
| OS | Windows 11，`10.0.22631`，64-bit | `CONFIRMED LOCAL` |
| 验证 Python | 外部 venv，Python `3.12.10`（与 CI major/minor 对齐） | `CONFIRMED LOCAL` |
| 初始系统 Python | Python `3.14.2`，缺少验证依赖，未用作绿色验证环境 | `CONFIRMED LOCAL` |
| Node | `v24.18.0`；CI 为 Node 22，存在版本差异 | `CONFIRMED LOCAL` |
| Git Bash | 显式路径 `D:\Program Files\Git\bin\bash.exe` | `CONFIRMED LOCAL` |
| 验证包 | AKShare `1.18.94`、FastAPI `0.141.1`、feedparser `6.0.14`、NumPy `2.5.2`、pandas `2.3.3`、pytest `9.1.1`、pytest-cov `6.3.0`、ruff `0.16.5`、Tushare `1.4.29`、SQLAlchemy `2.0.52`、Pydantic `2.13.4` | `CONFIRMED LOCAL` |

版本分层：有效 app `0.4.0`；有效策略 `signal-v0.4.0`；有效指标 `indicator-v0.2.0`；有效预测 `similarity-v0.2.0`。直接 v0.5 证据来自 `backend/app/utils/indicators_v05.py`、`backend/app/services/backtest_v05_service.py` 和相关 public service 调用，尚未成为当前 task-service 的 v0.5 有效链路。

## 4. 隔离基线验证

`CONFIRMED LOCAL`：绿色验证运行在隔离 source copy 中，而不是 owner-dirty 原始工作树；Windows SQLite fixture 先设置 session 临时 `REPORTS_DIR`，并在删除测试库前 dispose engine；绿色运行 `pytest -q` 为 **10 passed，exit 0**，无 teardown 错误。

同一隔离运行还通过：

- `python -m compileall -q backend/app`；
- `node --check backend/app/static/app.js`；
- 三个显式 Git Bash `bash -n` 部署脚本检查；
- scoped secret scanner。

扫描器排除 Git history、env 文件、vendor、reports、backups、caches；因此只说明扫描范围内无命中，不是这些排除区域清洁的证明。pytest 有非失败的 Starlette/httpx deprecation warning。上述结果不声明历史 Git/env 清洁，也不覆盖生产环境。

## 5. Tushare 能力矩阵

| 路径 | 单次观察 | 结论 |
|---|---|---|
| 初始化/配置 | `TUSHARE_TOKEN` missing | `BLOCKED` |
| instruments | 未初始化、未调用 | `UNVERIFIED` |
| daily history | 未调用 | `UNVERIFIED` |
| spot quotes | 未调用 | `UNVERIFIED` |
| news | 未调用 | `UNVERIFIED` |
| trade calendar | 未调用 | `UNVERIFIED` |

Tushare 是配置缺失而未调用，不是权限失败；接口权限和真实字段能力均未测试。

## 6. AKShare / Composite 单次 Provider 矩阵

以下是一次隔离能力运行的原始计数/延迟；`success` 不等于稳定性或交易级实时性。

| Provider / 操作 | status | records | latency | 备注 |
|---|---:|---:|---:|---|
| AKShare `list_instruments` | success | 5 | 0.017 ms | `PARTIAL`：单次 |
| AKShare `fetch_daily_bars` | success | 32 | 163.816 ms | `PARTIAL`：单次 |
| AKShare `fetch_spot_quotes` | success | 3 | 25,597.813 ms | 3 adapter-classified execution-grade-realtime、0 degraded；exchange-time/source-time freshness 未验证，仍是 `PARTIAL` |
| AKShare `fetch_news` | success | 0 | 0.001 ms | 空结果，新闻不可用，`PARTIAL` |
| AKShare `is_trade_day` | success | 1 | 0.001 ms | 返回 `true`，`verified=false`、provenance `unverified`，`UNVERIFIED` |
| Composite `list_instruments` | success | 5 | 0.069 ms | 实际 trace 为 AKShare，`PARTIAL` |
| Composite `fetch_daily_bars` | failure | 0 | 168.742 ms | `ProviderError`，`BLOCKED` |
| Composite `fetch_spot_quotes` | success | 3 | 22,009.333 ms | trace 为 AKShare；3 adapter-classified execution-grade-realtime、0 degraded；exchange-time/source-time freshness 未验证，`PARTIAL` |
| Composite `fetch_news` | success | 0 | 0.012 ms | 空结果，`PARTIAL` |
| Composite `is_trade_day` | success | 1 | 0.002 ms | `verified=false`、provenance `unverified`，`UNVERIFIED` |

Spot 调用在交易时段外；AKShare adapter 使用本地调用时间并将匹配行标为 `is_realtime=true`，没有证实 exchange-time/source-time freshness（交易所/源时间新鲜度）或稳定实时能力。Composite 的 daily 失败不能被独立 AKShare daily 成功抵消。该运行未启用 Mock fallback；不能据此声明稳定性，也不能形成 actionable signal。

## 7. Universe

| 项目 | 结果 | 状态 |
|---|---:|---|
| 总数 / enabled / disabled | 10 / 9 / 1 | `CONFIRMED LOCAL` |
| ETF / LOF / other | 9 / 1 / 0 | `CONFIRMED LOCAL` |
| SH / SZ | 9 / 1 | `CONFIRMED LOCAL`，由代码后缀派生 |
| duplicate symbol / ts_code | 0 / 0 | `CONFIRMED LOCAL` |
| theme_l1 / theme_l2 | 10/10 / 10/10 完整 | `CONFIRMED LOCAL` |
| benchmark | 4/10，6 缺失 | `PARTIAL` |
| explicit market 字段 | 无；market 由后缀派生 | `PARTIAL` |
| demo 标记 | 是 | `CONFIRMED LOCAL` |

本次可用于可靠真实研究的 ETF 数量是 **0（本轮验证为 0）**，不是 9；9 只是 Mock/配置中 enabled 的演示宇宙。

## 8. 历史数据质量

真实历史：`BLOCKED`。Tushare 未配置，Composite daily 在单次能力运行中失败；不能用 Mock 替代真实五只 ETF 交叉核对。

Mock 质量：`MOCK_ONLY`、9 个 enabled instrument × 301 行 = **2,709 bars**；每只覆盖 `2025-07-04` 至 `2026-08-28`，expected weekday coverage ratio 为 1。记录的重复日期、非单调日期、未来日期、OHLC 缺失/非有限/非正值、OHLC 关系、volume/amount 缺失/负值/非有限异常均为 **0**。来源集合只有 `mock`；这些是合成历史完整性结果，不是真实市场质量。

## 9. 指标验证

- `MOCK_ONLY / CONFIRMED LOCAL`：有效 v0.4 链 `IndicatorService.refresh_all -> app.utils.indicators.calculate_indicators` 创建 9/9 snapshots；版本为 `signal-v0.4.0`、`indicator-v0.2.0`、`similarity-v0.2.0`。有效链字段只完成可用/有限/范围检查。
- `MOCK_ONLY / PARTIAL`：直接 dormant `app.utils.indicators_v05.calculate_indicators` 对 5/5 Mock histories 均计算成功；对可用字段的 finite checks passed。ignition 五字段（`bars_since_ignition`、`last_ignition_low`、`last_ignition_high`、`last_ignition_volume`、`last_ignition_platform`）及 `pullback_volume_ratio`/`pullback_support` 仅在 2/5 histories available；证据未将缺失字段判为失败。它不是有效 v0.5 runtime。
- `CONFIRMED LOCAL / MOCK_ONLY`：public result frame 与独立 NumPy/pandas 本地参考公式的端到端比较通过：OBV、MFI14、CMF20 容差 `1e-9`；ADX14/+DI14/-DI14、RSRS beta/R2/raw/z-score 容差 `1e-8`。这是本地重复公式检查，不是外部可信指标库验证。
- 其余 MACD、KDJ、RSI14、ATR、BOLL、VWAP20、amount_ratio、volume_zscore20、CCI20、Williams_R14_28、ROC12、boxes/breakout/turtle 及相关结构字段，仅作可用性、有限性、范围或结构检查；没有独立公式核对，不升级为公式正确性证明。
- warm-up/default-fill（每个 301 行样本，账本记录但 harness 未作全量 runtime assertion）：MFI14 `13 default / 288 computed`（fill 50）；CMF20 `19 / 282`（fill 0）；ADX14、+DI14、-DI14 各 `13 / 288`（fill 0）；RSRS beta/R2/raw 各 `17 / 284`；RSRS z-score `46 / 255`（回归窗口 18、z-score 窗口 60、min_periods 30，fill 0）。
- RPS app：`UNVERIFIED`；只有 closed-form known-sequence reference self-check，当前没有 public app RPS 输出可比较。`volume_profile_approx` 明确是 estimated proxy，不是真实股东筹码分布；profit metric `UNAVAILABLE`。

没有安装外部可信指标库；没有 operation-level signal claim。

## 10. 轮动回测

`MOCK_ONLY_ENGINE_EXECUTION_PROOF`：当前有效 v0.4 rotation 使用 Mock，窗口 `2025-12-19` 至 `2026-08-28`，9 instruments，benchmark `510300.SH`。

| 指标 | 结果 |
|---|---:|
| total return | -9.6336% |
| annualized return | -0.13222 |
| benchmark return | -22.1640% |
| excess return | +12.5304 percentage points |
| maximum drawdown | -10.7584% |
| Sharpe | -2.3948 |
| Calmar | -1.229 |
| turnover / initial equity | 11.6597x |
| realized win rate | 0.5588 |
| average exposure | 0.4985 |
| decisions / trades | 36 / 134 |
| unavailable | Sortino、average holding days |

36 个 decision 均满足 `decision_at=close_t`、`execution_at=open_t_plus_1`、feature no-lookahead；显式 invariants 为 `all_feature_dates_at_or_before_decision=true`、`all_execution_dates_after_decision=true`、`future_data_in_features=false`。交易使用 100-share lots，成本配置存在。费用、滑点、迟滞、主题上限、市场门控目前是 source+config 证据，不是逐交易 exhaustive runtime assertions。正 excess 不能被称为“好表现”或策略优越性；这是 Mock 且 Sharpe 为负的受限引擎证据。

## 11. Ablation 与 v0.5 dormant 模块

当前 task-service 调用 `backtest_ablation` 返回 `UnknownTaskError`（预期阻断）。直接调用 dormant `RotationBacktestV05Service.run_ablation` 成功，但使用 `strategy_config_version=signal-v0.4.0`，状态为 `direct_dormant_service_only`、`not sealed; not runtime-wired v0.5 strategy`。

实际实现的是四个 variant；所有结果均 `MOCK_ONLY`，同一 observed non-factor controls/execution engine 下只改变 factor weights 的证据，未有 dataset hash 或 serialized effective-weight map，不能声称密码学意义的 common input identity。

| variant | total return | annualized return | Sharpe | Sortino | max drawdown | turnover / initial equity | realized win rate | trades | average holding days | average exposure | benchmark return | excess return |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| momentum_baseline | -0.094776 | -0.130121 | -2.3678 | null | -0.107737 | 11.0189 | 0.5362 | 136 | null | 0.4969 | -0.22164 | 0.126864 |
| plus_volume_flow | -0.125830 | -0.171610 | -3.0594 | null | -0.138335 | 12.1896 | 0.4478 | 137 | null | 0.5036 | -0.22164 | 0.095810 |
| plus_breakout_structure | -0.138945 | -0.188958 | -3.4651 | null | -0.151262 | 12.3165 | 0.4286 | 143 | null | 0.5036 | -0.22164 | 0.082695 |
| full_v050 | -0.122865 | -0.167675 | -3.0069 | null | -0.135410 | 11.4060 | 0.4507 | 144 | null | 0.5036 | -0.22164 | 0.098775 |

`Sortino` 与 `average_holding_days` 的 `null` 是批准证据中的 unavailable/null，不是补算值；ablation variant sanitized schema 未报告 Calmar，故本表不列该列。相对 `momentum_baseline` 的 Δreturn / ΔSharpe / ΔMDD / Δturnover 仍分别为：baseline `0 / 0 / 0 / 0`；volume-flow `-0.031054 / -0.6916 / -0.030598 / +1.1707`；breakout-structure `-0.044169 / -1.0973 / -0.043525 / +1.2976`；full-v050 `-0.028089 / -0.6391 / -0.027673 / +0.3871`（MDD 更负表示更差）。

在这一次 Mock 运行中，`full_v050` 在 return、Sharpe、最大回撤和 turnover 四项都不优于 `momentum_baseline`；这不是晋级决定。请求的 A-H variants 未实现/不可用；不据此调参或修改阈值。

## 12. Forecast 验证

`MOCK_ONLY` rolling-origin audit，模型 `similarity-v0.2.0`，27 个 snapshot 全为 `not_calibrated`。时间顺序与 rolling origin 由验证服务报告，未 shuffle；每 instrument 样本稀疏（horizon 1/5/20 分别约 25/24/21）。

| horizon | instrument_count | samples | directional accuracy | Brier | return MAE | 80% coverage |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 9 | 225 | 0.488889 | 0.253040 | 0.009076 | 0.786667 |
| 5 | 9 | 216 | 0.425911 | 0.265240 | 0.022414 | 0.768533 |
| 20 | 9 | 189 | 0.486756 | 0.283659 | 0.044369 | 0.693133 |

Calibration bins（`range: count / mean predicted / actual frequency`）：h1 `0.2-0.4: 8/0.3869/0.625; 0.4-0.6: 212/0.4854/0.467; 0.6-0.8: 5/0.6425/0.8`；h5 `0-0.2: 2/0.1896/0.5; 0.2-0.4: 55/0.3471/0.4545; 0.4-0.6: 144/0.4899/0.5139; 0.6-0.8: 15/0.6284/0.4`；h20 `0-0.2: 7/0.1417/0.2857; 0.2-0.4: 87/0.3127/0.5632; 0.4-0.6: 73/0.4822/0.411; 0.6-0.8: 20/0.6769/0.5; 0.8-1.0: 2/0.8187/0`。`instrument_count=9` 是每个 horizon 的聚合覆盖数；此前所述每 instrument 约 25/24/21 是 `sample_count ÷ 9` 的平均数，不是证据展示的逐 instrument 分布。

没有简单 forecast baseline、显著性分析或真实数据校准；不得把这些数称为生产预测性能，也不得把状态改成 `calibrated`。

## 13. 已知缺口与风险

- Provider smoke/audit/log 路径仍需要经单独设计批准的 raw error redaction 与审计字段治理；本报告不读取或回显 raw error。
- calendar provenance、spot 交易所时间与 freshness 尚未验证；单次 spot 慢延迟不能推出稳定实时能力。
- 没有真实五只 ETF 的 OHLCV/复权/字段 schema/source-time 交叉核对；当前 universe 是 demo 配置，benchmark 仅 4/10。
- 真实停牌、无成交、涨跌停无法成交、LOF 溢价、现金收益、交易约束及独立第二引擎 reconciliation 尚未完成；逐交易 caps/fees/slippage/hysteresis 也未穷尽断言。
- `FILE_MANIFEST.txt`、`SOURCE_INFO.json`、示例 artifacts 和部分 docs/manifest 相对当前 HEAD 可能过时，未在本轮静默重写。
- effective runtime 仍是 v0.4；v0.5 dormant indicator/backtest 未完成 runtime wiring/strategy sealing；报告/测试存在已记录 deprecation warning。

## 14. Handoff 十问

1. **当前真实数据稳定性？** `BLOCKED`：本轮可靠真实研究计数为 0。单次 AKShare 成功、Composite daily 失败，不能声明稳定。
2. **Tushare 接口？** `BLOCKED/UNVERIFIED`：已实现路径未调用，因配置缺失；权限不是失败而是未测试。
3. **AKShare 稳定性？** `PARTIAL`：一次 list/daily/spot/news/calendar 观察；spot 约 25.6 秒且交易时段外，Composite daily 仍失败，无稳定性结论。
4. **可靠 ETF 数量？** **0（本轮真实验证）**；enabled 9 只是 Mock/demo universe。
5. **已验证指标？** `MOCK_ONLY`：本地参考公式端到端通过 OBV、MFI14、CMF20、ADX-DMI、RSRS；直接 dormant v0.5 五个历史的字段检查通过。RPS app `UNVERIFIED`。
6. **最佳 family？** 仅在本次 Mock ablation 中，`momentum_baseline` 四项优于其他实际 variant；不能称真实最佳。
7. **full vs momentum？** Mock dormant 结果中 `full_v050` 在 return、Sharpe、MDD、turnover 均不优于 momentum；不是晋级结论。
8. **哪些新增指标尚未证明增量？** 所有新增 v0.5 family 都没有真实增量证据；volume-flow、breakout-structure、full 在该 Mock run 反而变差；A-H 未实现，RPS app 未验证，volume profile 只是 estimated。
9. **forecast 表现？** h1/h5/h20 DA 为 0.488889/0.425911/0.486756，Brier 为 0.253040/0.265240/0.283659，80% coverage 为 0.786667/0.768533/0.693133；样本稀疏、无 baseline/显著性，状态 `not_calibrated`。
10. **下一步 top 3-5？** 见下一节；优先补真实数据与 provenance，再处理 runtime alignment、回测现实约束和 forecast calibration。

## 15. 优先级方向（3-5 项）

1. **真实 Provider 能力与数据契约**：在独立批准后，对 Tushare 配置、AKShare/Composite、5 ETF 历史、spot freshness、calendar provenance 做最小可审计 smoke；Provider 行为或 raw-error redaction 改动前必须另行完成设计批准。
2. **运行时版本对齐**：由 Jovi 决定 v0.6 方向后，再把 v0.5 indicator/backtest/signal 以明确版本、输入哈希和任务注册接入有效链，更新 stale manifest/docs，不覆盖 owner work。
3. **真实回测与第二引擎对账**：补齐停牌/成交量为零/涨跌停/LOF premium/cash yield/交易约束，并对 caps、fees、slippage、hysteresis 做可重复逐交易断言；不从 Mock 结果调阈值。
4. **Forecast 校准**：加入简单 baseline、样本量/显著性报告、真实 rolling-origin 数据和人工批准记录；保持 `not_calibrated` 直到封版条件满足。
5. **页面/新闻路线选择**：在数据/provider/page/news 与 v0.6 之间等待 Jovi 决策；新闻保持空结果/不可用事实边界，LLM 不生成操作级信号。

## 16. 证据索引

| 证据 | 完整路径 | SHA-256 |
|---|---|---|
| Provider capability sanitized | `E:\Claude_allow\Download\etf-v050-baseline-20260828-010724-5733a2a2a57a4769bb639ada797e2cfb\evidence\provider-capability-sanitized.json` | `c556af27ab344eb899540e05e8d56e457ca061d05947e01a8592e34ed1fcf3ee` |
| Task 4 history/indicator sanitized | `E:\Claude_allow\Download\etf-v050-baseline-20260828-010724-5733a2a2a57a4769bb639ada797e2cfb\evidence\task4-mock-history-indicators-sanitized.json` | `F9916837181E9792A3EA95336E6B3E96E57B1A3AF7367BD525052032E434359D` |
| Task 5 backtest/forecast sanitized | `E:\Claude_allow\Download\etf-v050-baseline-20260828-010724-5733a2a2a57a4769bb639ada797e2cfb\evidence\task5-mock-backtest-forecast-sanitized.json` | `1335de0015bffa07bc21baf3c319a71f1b368b9f7acae94af7c092cf661fcb3b` |
| 隔离运行 root | `E:\Claude_allow\Download\etf-v050-baseline-20260828-010724-5733a2a2a57a4769bb639ada797e2cfb` | 目录；本账本未记录目录 SHA |

复现限制：run root 没有目录 hash，也没有持久化的完整 command manifest；因此 replayability 为 `PARTIAL`，不是 validation failure。本报告引用 sanitized evidence 与账本中的隔离运行结论；不引用 raw logs、raw provider records、secret files、public IP、signed URL 或外部 URL。

## 17. 最终状态与阻断摘要

**PARTIAL / NOT READY FOR REAL STRATEGY SEALING OR PRODUCTION PROVIDER CLAIMS**。

主要 blocker：Tushare configuration missing；Composite daily single-run failure；没有真实五 ETF 交叉验证；有效 runtime 仍 v0.4；`backtest_ablation` 未注册；forecast 全部 `not_calibrated`；尚无真实校准、完整回测现实约束和人工策略封版记录。

请等待 Jovi 决定下一条路线：**v0.6 runtime/strategy、data/provider、page 或 news**。在决定和相应设计批准之前，不应宣称真实 Provider 稳定、不应封版 v0.5、不应部署生产 Provider，也不应产生任何真实投资建议。
