# 沪深300 头部基金市值/流通市值比例：数据源选型

日期：2026-10-29；状态：SELECTION，未实现取数，未进入评分。
配套设计：`tasks/plans/2026-10-28-hs300-passive-ratio-research.md`。

## 0. 口径先校准（重要）

Jovi 的目标表述是「头部沪深300基金市值占沪深300**流通市值**比例」，因此：

- 分母口径 = **流通市值**（float market cap），不是自由流通市值。
- 指标命名改为 `hs300_passive_share_of_float_mv`。
- 若将来采用自由流通口径（`free_share × close`），必须单列
  `hs300_passive_share_of_free_float_mv`，两者不得混用或互相替代。
- 分子 = 头部沪深300 跟踪 ETF 的基金市值；优先 AUM（份额 × 单位净值），
  次选二级市场市值（份额 × 收盘价），两者必须用不同字段名标注。

## 1. 已核实的候选源（2026-10-29）

### 1.1 分子：基金份额（已具备）

- 现有适配器 `backend/app/providers/share_scale.py`：
  - 上交所 `fund_etf_scale_sse(date)`，AKShare 已把万份换算为份；
  - 深交所 `fund_scale_daily_szse(...)`，缺失时回退 `fund_etf_scale_szse()`。
- 已在 `bounded_sdk.AKSHARE_APIS` 白名单内，已有持久化 `EtfShareScale`。
- 结论：**直接复用**，无需新源。

### 1.2 分子：净值 / 规模

| 候选 | 能力 | 限制 | 结论 |
|---|---|---|---|
| 份额 × 本地收盘价 | 现有 bars + shares，纯本地 | 是市值代理，不是净值；溢价/折价通常 <1% | **第一阶段采用**，字段名 `market_value_at_close` |
| AKShare `fund_etf_fund_daily_em` | 全市场场内基金快照，列名自带净值日期 | 不在 `AKSHARE_APIS` 白名单；HTML 解析脆弱 | 暂不接入，需单独评审 |
| AKShare `fund_etf_fund_info_em` | 单基金历史净值 | 每只基金分页拉取，请求量大 | 不采用 |
| Tushare `fund_nav` | 含 `net_asset`（资产净值） | ≥2000 积分；不在 `TUSHARE_APIS` 白名单 | 可选升级项，需评审 |
| Tushare `etf_share_size` | `total_size`（总规模） | ≥8000 积分 | 不采用（门槛过高） |

### 1.3 分母：沪深300 流通市值

| 候选 | 能力 | 限制 | 结论 |
|---|---|---|---|
| Tushare `daily_basic` | 全 A 股按交易日：`close`、`total_mv`、`circ_mv`（万元）、`free_share`（万股）；单次 6000 条 | ≥2000 积分；需按交易日循环 | **首选**（可回填历史） |
| Tushare `index_weight` | 沪深300（`399300.SZ`）月度成分与权重，权重为百分比数值 | ≥2000 积分；不在白名单 | **首选配套**（成员历史） |
| Tushare `index_dailybasic` | 指数每日指标含 `float_mv` | 官方文档：仅覆盖上证综指、深证成指、上证50、中证500、中证1000、中小板指、创业板50、创业板指、科创50，**不含沪深300** | **排除**（已核实） |
| AKShare `stock_zh_a_spot_em` | 全 A 股快照含总市值/流通市值；已在白名单 | 只有当日快照，无历史，不能回填 | 无凭证兜底（前瞻积累） |
| 中证官方成分 `index_stock_cons_csindex` | 官方成分名单（含日期） | 仅当前名单 | 成分过滤/兜底 |
| 中证官方权重 `index_stock_cons_weight_csindex` | 官方权重（%） | 仅权重，无市值 | 交叉校验 |
| 中证估值 `stock_zh_index_value_csindex` | 市盈率/股息率 | 无市值 | 排除 |
| 中证行情 `stock_zh_index_hist_csindex` | OHLC/成交额/滚动市盈率 | 无市值 | 排除 |
| 中证未文档化 JSON 接口 | 未知 | 实测 `/index-basic-info` 返回 404；不得写死猜测接口 | 排除 |
| Wind / Choice / iFinD | 完整 | 商业许可与成本 | 排除（个人项目） |
| BaoStock / 新浪行情 | 无市值字段 | 能力缺失 | 排除 |

### 1.4 项目现状（决定实现成本）

- `backend/app/core/config.py` 已有 `market_provider`（含 `tushare`）与
  `tushare_token`（`repr=False, exclude=True`），token 已有配置入口。
- `backend/app/providers/bounded_sdk.py` 的 `TUSHARE_APIS` 白名单目前为
  `index_daily, etf_basic, fund_basic, fund_daily, rt_etf_k, etf_mins,
  trade_cal, news, major_news, cctv_news`；`daily_basic`、`index_weight`、
  `fund_nav` **不在其中**，启用需显式扩白名单并复审。
- `backend/app/providers/catalog.py` 已使用 `etf_basic` 并解析 `index_name`，
  可用于派生「跟踪沪深300」的 ETF 清单，不依赖名称猜测。

## 2. 结论

### 推荐方案 A（可回填、可验证）：Tushare 2000 积分路径

- 分母：逐交易日 `daily_basic` → 按 `index_weight` 的当期成分过滤 →
  `Σ circ_mv`（万元 → 元）。
- 分子：现有份额 × 本地收盘价（市值代理）；后续可升级 `fund_nav.net_asset`。
- 交叉校验：计算隐含权重 `circ_mv_i / Σ circ_mv`，与官方
  `index_weight.weight`（百分比数值）比较，输出 Spearman 相关与最大偏差；
  偏差超阈值即 `unavailable`，不输出比例。
- 优点：可回填多年历史，能直接支撑设计文档要求的 walk-forward；
  不新增供应商（项目已声明 `market` extra 含 `tushare`）。
- 代价：需要 Jovi 确认账号积分与条款；需扩白名单并复审。

### 兜底方案 B（零新凭证、只能前瞻）：AKShare + 中证官方名单

- 成分：`index_stock_cons_csindex`（官方，当前名单）。
- 分母：`stock_zh_a_spot_em` 全 A 股流通市值快照，按成分求和。
- 只能在每个交易日收盘后采集并落库，**从接入日开始积累**；
  无法回填，样本不足前比例始终 `status=unavailable`。
- 适合作为方案 A 未获批时的最小可行路径，不得宣称可校准。

### 不采用

- `index_dailybasic`（不含沪深300）、中证估值/行情接口（无市值）、
  未文档化接口、商业终端。

## 3. 实现前的准入清单

1. Token 只从环境变量/设置读取，不写入仓库、日志、报告或截图。
2. 新端点加入 `TUSHARE_APIS` 白名单，逐端点写明用途、参数边界与返回上限。
3. 新增 provider 能力（建议）：
   - `fetch_index_membership(index_code, start, end)`
   - `fetch_stock_float_market_caps(trade_date)`
   - 纯函数 `hs300_passive_share_of_float_mv(...)` 只接收已校验序列。
4. 失败关闭条件：成分覆盖 <100%、交易日不一致、单日股票覆盖 <99.5%、
   权重校验偏差超阈值、token/权限不足、滞后超过 T+1、单位为未知。
5. 落库只进研究快照，不与生产行情表混用；不改变 `actionable`、`state`、
   仓位建议与资格状态。
6. 许可状态记录为 `REVIEW_REQUIRED`：Tushare 个人使用条款、站点展示派生
   数据的再分发边界，未确认前只在本机研究视图展示。

## 4. 待 Jovi 决定

1. 是否启用 Tushare（≥2000 积分）；若启用，是否同意扩白名单。
2. 「头部」定义：top N（建议先 top 3 与 top 5 两档）与基金清单
   （由 `etf_basic.index_name` 派生候选后人工确认）。
3. 分子口径：先上线「份额 × 收盘价（市值代理）」，还是等 `fund_nav`
   净值为准。

## 5. 证据来源

- Tushare `index_dailybasic` 文档（覆盖指数清单、2000 积分、字段单位）：
  https://tushare.pro/document/2?doc_id=128
- Tushare `daily_basic` 文档（`circ_mv`/`total_mv` 万元、`free_share` 万股、
  6000 条上限、2000 积分）：https://tushare.pro/document/2?doc_id=32
- Tushare `index_weight` 文档（月度、权重为百分比数值、2000 积分）：
  https://tushare.pro/wctapi/documents/96.md
- Tushare `fund_nav` 文档（`net_asset`、2000 积分）：
  https://tushare.pro/document/2?doc_id=119
- 本地安装的 AKShare 1.20.x 源码：`fund_etf_sse.py`、`fund_em.py`、
  `stock_hist_em.py`、`index_cons.py`、`index_stock_zh_csindex.py`。
