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
  卡片上标注数据源与版本。某日缺正式收盘价时，仅当最新价落在当日最高最低之间才用它暂代，并标 `provider_last_price_provisional`，
  卡片显示“含暂代收盘价”。拿不到的代码写入 `failed_tickers` 并如实显示，不用别的数据补。
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
