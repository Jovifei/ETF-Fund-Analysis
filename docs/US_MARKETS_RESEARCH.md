# 美股 CPO / 存储 / 纳指 / 标普 500 研究区块

> 标签：`research_only` · `actionable=false` · `not_calibrated` · `changes_grade=false`
> 本区块只做展示。不进入 `assign_grade`、五级评分、仓位、信号或策略邮件。

## 它是什么

总览页（`/`）新增一张“美股 CPO · 存储 · 指数（研究）”卡片：

| 序列 | `series_id` | 口径 |
|---|---|---|
| 美股 CPO/光模块（宽口径等权） | `us-cpo-optical-broad-ew` | COHR LITE FN AAOI CIEN ANET AVGO MRVL CRDO |
| 美股 光硬件（窄口径等权） | `us-cpo-optical-narrow-ew` | 前 5 只 |
| 美股 存储（等权） | `us-memory-storage-ew` | MU WDC STX SNDK |
| 标普 500 / 纳指 100 / 纳指综合 | `us-sp500` `us-nasdaq-100` `us-nasdaq-composite` | 官方指数（^GSPC ^NDX ^IXIC） |

篮子是自定义研究口径，不是官方指数。等权、按日再平衡；上市较晚的成分按上市日起逐步扩容（至少 3 只才计值）。
每个序列给出：1 周/1 月/3 月/6 月/今年/1 年收益、当前回撤与最大回撤、ATR%（`atr_pct_fixed_v1` 分档）、道氏代理、
威科夫代理（仅指数；合成篮子没有成交量，标“未计算”）、相对标普/纳指的超额收益与日收益相关、近一年走势。
篮子另带成分表、口径说明和覆盖缺口。

## 设计

- 独立模块 `backend/app/us_markets_research/`：`contracts.py`（无 pandas，校验）、`providers.py`（行情源）、
  `compute.py`（篮子与指标）、`builder.py`（组装与输出）、`store.py`（读取与读模型）。
- 结构列直接复用仓库已有的 `research/etf_structure_features`（ATR 分档、道氏确认枢轴、威科夫 OHLCV 代理），不重写规则。
- 配置 `config/us_markets_research.json`（成分、口径、哈希写入快照）。**没有改** `config/market_context.json`、数据库、alembic，也没有新增 `context_kind`。
- 展示链路：`us_markets_research` 作为 local-display-v2 展示包的**可选 part**。
  - `local_display_contract.OPTIONAL_PARTS` 加入该 part，并在 `verify_bundle_integrity` 里按契约校验（`actionable` 必须为 false、
    `calibration_status` 必须为 `not_calibrated`、数值必须有限）。校验失败整包拒收。
  - `local_compute` 仅当环境变量 `US_MARKETS_RESEARCH_SNAPSHOT_PATH` 指向有效快照时才附加该 part；**默认不设置，展示包与现在逐字节一致**。
  - 读取：`LocalDisplayReader.read_us_markets_research_view` 与 `GET /api/workspace/us-markets-research?generation=`。
    网站按总览同一批次号读取，不会拿别的批次或实时行情顶替；缺失就显示“尚未发布”。
  - 非展示包模式（本地开发）下，同一接口直接读该环境变量指向的快照文件，便于本机查看。
- 行情源：生产里官方美股指数卡片仍用原有新浪通道，本区块不替代它。篮子与指数对照序列用 yfinance（免费、非官方），
  卡片上标注数据源与版本。缺失日收盘或复权收盘时直接排除，绝不以 last_price 或跨日复权因子补齐。
  导入旧 CSV 时剔除所有 provisional 观察，记录 `excluded_provisional_observations`。篮子任一应有成分出现内部缺口时只发布缺口前连续段，不填零、不临时缩减成分。
  拿不到整个代码时该篮子不可用；输出 `failed_tickers`，不以其他数据补。
- 全部输出为 UTF-8、LF；不依赖 PowerShell 默认编码。

## 生成数据（含 2018 起回补）

```powershell
chcp 65001
$env:PYTHONUTF8 = "1"
python scripts/build_us_markets_research.py --out-dir <明确的输出目录> --source yfinance
# 离线复现： --source csv --csv us_daily_ohlcv.csv --as-of 2026-11-13
```

输出（`--out-dir` 必填，不设默认值，绝不写实盘数据根）：
`us_markets_research_snapshot.json`（展示快照）、`us_markets_research_history.csv`（2018 起每个序列的日线 OHLC 水平）、
`us_markets_research_source_audit.json`（每个代码的 provider/操作/耗时/行数/原因）。

## 本机查看

```powershell
$env:US_MARKETS_RESEARCH_SNAPSHOT_PATH = "<out-dir>\us_markets_research_snapshot.json"
# 使用隔离的测试库启动（与 frontend/playwright.config.ts 相同的环境），打开 http://127.0.0.1:<port>/
```

## 上线前仍需（需用户逐步批准）

任何一步都不在本分支内执行。

1. **先对齐基线。** 本分支基于 `origin/main`；线上实际运行的 `98ba055`（`codex/sector-drawer-v1-20261108`）不在 `main` 里。
   上线前需先决定合并顺序，再在目标基线上重跑本区块的测试。
2. **先部署服务端，再开启生产者开关。** 旧服务端不认识 `us_markets_research` part，会整包拒收。
3. 在本机计算环境确认可用 `yfinance`（`pip install "yfinance>=0.2.40,<2"`），并新增一个独立的每日任务：
   美股收盘后（北京时间次日早晨）运行 `scripts/build_us_markets_research.py --out-dir <固定目录>`。该任务与 `ETF-Local-Live-Compute`、通知任务无耦合。
4. 在 `ETF-Local-Live-Compute` 的环境里设置 `US_MARKETS_RESEARCH_SNAPSHOT_PATH`（生产配置变更，需单独批准），下一个批次起展示包带上该 part。
5. 网站验收：总览出现卡片，批次号与总览一致，`as_of` 为最近美股交易日。
6. 回滚：取消该环境变量即可，展示包恢复为原样；卡片显示“尚未发布”。


## 2026-11-14 数据质量修订（必须阅读）

- 旧版 `4aa7066` 的暂代价结果已撤回，旧快照因缺 `price_policy` 被新验证器拒收；不是把 UI 改个标签继续混用。
- 仅使用 provider 自报的日线 Close 与 Adj Close；不声称获得交易所认证数据。仍是 UNKNOWN / not_calibrated。
- SNDK 仅从 **2025-02-24** regular-way 开始使用，2025-02-13 至 02-21 when-issued（SNDKV）全部排除。
  2016 年以前的老 SNDK 不是本研究这家独立公司的连续历史，不能接进来。首次可贡献日收益为 02-25。
- CRDO 从 2022-01-27 开始；COHR 2022-09 以前是 II-VI 前身历史，不是原 Coherent Inc. 同质业务。
- WDC 2025-02-24 分拆：旧 CSV 将该日公司行动编码为 Stock Splits=1.323；这是供应商编码，
  **不是独立核实的拆股经济含义**。供应商复权是否完整处理分派尚未与公司行动台账独立对账；不自造分派收益。
- 当前名单回溯不等于 point-in-time 投资组合。未取得历史选样/退市数据库，明确标
  `current_2026_11_14_constituents_retrospective_not_point_in_time`，不能报告可投资回测或晋级实盘资格。
- 交易日历是本次已观察到的代码日线的 union calendar，不是交易所认证日历。
  每个序列按上市起点重索引，缺口不能压缩成“相邻交易日”。所有代码都缺失的日子仍属日历覆盖限制。
- RS 的 `first_overlap / last_overlap / n_price_pairs / n_daily_return_pairs / n_union_sessions / n_missing_sessions`
  区分价格对和相邻日收益对。相关在 union calendar 的连续日收益上计算（no-fill），而不是把缺失日 drop 后跨日拼接。
- 合成篮子 high/low 是各成分单日高低的组合包络，不是同时可交易篮子的实际高低；ATR 与道氏仅合成代理，威科夫不算。
- 旧报告中美股 D→下个 A 股交易日的相关数值与样本数未在本分支重审，不随本模块上线；旧研究结论撤回，不沿用。

### 原始证据（2026-11-14 本轮打开/检索）

1. Sandisk 正常交易与完成分拆：
   https://www.sandisk.com/company/newsroom/press-releases/2025/sandisk-celebrates-nasdaq-listing-after-completing-separation
2. Sandisk 8-K，when-issued 区间 SNDKV：
   https://investor.sandisk.com/static-files/04f70eee-4588-4ee6-8b77-88f21efdc417
3. CRDO IPO 定价公告：
   https://www.globenewswire.com/news-release/2022/01/27/2373939/0/en/Credo-announces-pricing-of-initial-public-offering.html
4. II-VI 更名 Coherent：
   https://www.coherent.com/news/press-releases/ii-vi-changes-name-to-coherent-and-launches-new-brand

### 无生产副作用的本地演示（box）

```bash
cd /workspace/etf-us-markets-quality-20261114
export PYTHONUTF8=1 PYTHONPATH="$PWD/backend" APP_ENV=test AUTH_ENABLED=false
export MARKET_PROVIDER=mock ALLOW_MOCK_FALLBACK=false AUTO_CREATE_SCHEMA=true
export DATABASE_URL=sqlite:////tmp/workspace-e2e-us-quality.sqlite3
export REPORTS_DIR=/tmp/etf-us-quality-reports WORKSPACE_UI_ENABLED=true
export US_MARKETS_RESEARCH_SNAPSHOT_PATH=/workspace/etf_us_markets_20261114/corrected_fresh/us_markets_research_snapshot.json
/workspace/etf-display-venv/bin/python scripts/workspace_smoke_seed.py
/workspace/etf-display-venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 18093
# 打开 / 与 /research；仅测试隔离库，无生产登录、无上传、无定时任务变更。
```

独立研究页 `/research` 与总览复用同一卡片；本地展示模式先捕获 overview generation 后再读同批研究数据。
缺批次时不发未固定批次的请求。本文演示命令由使用者显式运行，本轮不启动持久服务器。
