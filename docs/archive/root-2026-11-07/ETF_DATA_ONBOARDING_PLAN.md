# ETF 数据接入方案与免费通道实测

> 日期：2026-09-02 · 状态：核心通道已跑通，K线/板块降级已修复并验证

## 一、结论先行

决策看板"没有 ETF 数据"不是代码没合并，而是**数据库从未灌入数据**：

- `SCHEDULER_ENABLED=false` → 数据同步任务链从没执行过；
- `MARKET_PROVIDER=mock` → 即便执行也是假数据。

数据接入代码（akshare/tushare/ftshare/composite 全套 provider、板块服务、K线企稳）**早已合入 main**，自选池 `config/watchlist.json` 有 37 只 ETF+LOF（含标普500/纳斯达克跨境）。

## 二、免费通道实测矩阵（容器内 akshare 1.18.94）

| 数据 | 首选通道 | 状态 | 降级通道 | 状态 |
|---|---|---|---|---|
| ETF 实时行情 | 东财 `fund_etf_spot_em` | ✅ 1597 只 | — | — |
| ETF/LOF 历史K线 | 东财 `fund_etf_hist_em` | ❌ 反爬断连 | 新浪 `fund_etf_hist_sina` | ✅ 3468 行 |
| 行业板块（涨跌家数） | 东财 `stock_board_industry_name_em` | ❌ 反爬断连 | 同花顺 `stock_board_industry_summary_ths` | ✅ 90 行业 |
| 概念板块（涨跌家数） | 东财 `stock_board_concept_name_em` | ❌ 反爬断连 | 同花顺 `stock_board_concept_summary_ths` | ⚠️ 50 概念，**无涨跌家数** |
| 全市场宽度 | 新浪 `stock_zh_a_spot` | ✅ 涨1541/跌3900 | 腾讯 `qt.gtimg.cn` | ✅（已有代码） |
| 上证指数 | 新浪 `stock_zh_index_daily` | ✅ 8717 行 | — | — |
| 中证全指 | 新浪 `stock_zh_index_daily` | ✅ 1180 行 | — | — |
| 标普500 | 新浪 `index_us_stock_sina` | ✅ 5705 行 | — | — |
| 纳斯达克 | 新浪 `index_us_stock_sina` | ✅ 5702 行 | — | — |
| Tushare | 需 token | 未配置 | — | 非免费 |

**关键现象**：东财对 `board/*.em`（板块）和 `fund_etf_hist_em`（K线）接口做了反爬断连，
但 `fund_etf_spot_em`（ETF 实时行情）正常。免费层需要靠「新浪 + 同花顺」补齐 K线和板块。

## 三、本次修复（已实现 + 已验证）

发现并修复了 1 个 main 上的真实 bug + 2 处降级缺口：

1. **`CompositeProvider` 缺板块方法（真实 bug）**：`public_composite`/`composite` 模式下，
   `fetch_sector_snapshots` / `fetch_concept_snapshots` / `fetch_market_breadth` 三个方法
   未在 composite 层转发，调用时直接落到 base 类默认抛 `CapabilityUnavailable`，
   导致板块数据在真实源模式下**永远为空**。已补齐三个转发方法（`composite.py`）。

2. **K线无降级**：`fetch_daily_bars` 只走东财，被断即整体失败。已加新浪 `fund_etf_hist_sina`
   降级（`akshare.py`，拆分 `_fetch_daily_bars_em` / `_fetch_daily_bars_sina`）。

3. **概念板块无降级**：`fetch_concept_snapshots` 只走东财。已加同花顺 `stock_board_concept_summary_ths`
   降级，用「成分股数量」填充 total_count，涨跌家数置空（消费侧显示 "—"）。

验证结果（容器内实测）：
- 行业板块 90 个（军工装备 涨56/跌24）；
- 概念板块 50 个（MLCC概念 37 成分股）；
- 全市场宽度 涨1541/跌3900；
- K线 510300.SH 新浪源 18 根（2025-01）。

## 四、仍需补齐（后续迭代）

1. **概念板块涨跌家数**：免费层暂无稳定可用源（东财断、同花顺无涨跌家数、新浪 `stock_sector_spot('新浪概念')` 有 akshare 内部 bug）。
   可选方向：① 东财行情中心概念列表接口（需绕过反爬）；② 用同花顺概念成分股 + 个股行情自行聚合涨跌家数。
2. **A股/美股大盘基准**：当前 watchlist 已用 `510300.SH`（沪深300）作门控基准、`513500/513100`（QDII ETF）代理美股。
   如需真实指数，可用新浪 `stock_zh_index_daily`（上证/中证全指）和 `index_us_stock_sina`（标普/纳指）——通道已实测可用，待接入 `market_context` 或新增指数表。
3. **Tushare 增强**：免费层够用；注册 token 后可开 `composite`（tushare 优先）提升板块/复权精度。

## 五、当前配置切换

`.env` 已切到免费真实源（本次已改）：
- `MARKET_PROVIDER=public_composite`（AKShare 为主，有 token 自动加 Tushare）
- `SCHEDULER_ENABLED=true`
- `ALLOW_MOCK_FALLBACK=false`（Mock 结果阻断 actionable，安全）

首次跑通后的数据量：instruments 36 只、spot_quotes 35 条；K线/板块快照待 scheduler 后续周期补满。

## 六、第二批接入（已完成，2026-09-02 续）

### 概念板块新浪降级
降级链扩展为 **东财 → 新浪 → 同花顺**：
- 新浪 `stock_sector_spot(indicator='概念')` 返回 175 个概念，含板块涨跌幅 + 公司家数。
  ⚠️ 参数必须是 `"概念"`（传 `"新浪概念"` 会触发 akshare 内部 `UnboundLocalError` bug）。
- 比同花顺（50 个、无涨跌幅）多 125 个概念，且多了 pct_change。
- 仍无「涨跌家数」字段（新浪/同花顺都不提供，仅东财有但被反爬），up/down 置空显示 "—"。

### A股 / 美股大盘指数接入
给 akshare 实现 `fetch_market_context`（index kind）：
- A股：`stock_zh_index_daily` → 上证 `sh000001`、沪深300 `sh000300`、中证全指 `sh000985`
- 美股：`index_us_stock_sina` → 标普500 `.INX`、纳指综合 `.IXIC`、纳指100 `.NDX`
- 新浪日线无涨跌幅字段，用最后两根 close 推算 pct_change
- 配置 `market_context.json` 新增 3 个 A股指数卡片 + 开启 3 个美股指数（enabled + source_symbol + verified）

实测 6 指数全部真实落库（is_mock=false）。

### 可交易代理（tradable_proxy）接入
- akshare `fetch_market_context` 增加 `TRADABLE_PROXY` 分支，用 `fetch_spot_quotes` 拉 ETF 实时价。
- 启用 `china-semiconductor-etf`：source_symbol=512480（半导体ETF国联安），display_code=512480.SH。
- ⚠️ 契约约束：`source_timestamp <= fetched_at`；ETF quote_time 由 fetch_spot_quotes 内部 now 生成，
  可能晚于外层 fetched_at，需取两者较晚者作 fetched_at。

### 关键约束备忘
- 非 mock 的 `MarketContextObservation` 必须 `verification_status=VERIFIED`，否则 `_validate_observations` 抛错。
- 前端 `DEFAULT_MARKET_CONTEXT` 是兜底默认，后端新增卡片经 `mergeMarketContext` 的 extras 分支自动显示，无需改前端。
- 最终数据量：行业 90 / 概念 175 / 全市场 1 / 大盘指数 6 / 可交易代理 1 / K线 20691。

## 七、仍待补齐

1. **概念板块涨跌家数（免费层客观无法根治，已穷尽探测）**：东财所有概念接口（name_em/concept_em/hist_em/cons_em）全被反爬断连；同花顺概念 summary 无涨跌家数且无成分股函数；新浪概念仅有板块涨跌幅+公司家数；富途概念 JSON 解析失败。免费层只能提供「概念名 + 成分股数量 + 板块涨跌幅」，涨跌家数需 Tushare token（切 composite，tushare 优先）或东财反爬缓解后补。不绕反爬（违反"不在业务层硬编码网页接口"原则）、不做成分股聚合（175 概念 × 成分股逐只拉行情成本过高）。
2. **韩国半导体可交易代理**：`korea-semiconductor-etf` 卡片尚未接数据源（国内免费源对韩国 ETF 覆盖差）。
3. **Tushare 增强**：注册 token 后切 `composite`（tushare 优先）可提升板块涨跌家数与复权精度。


