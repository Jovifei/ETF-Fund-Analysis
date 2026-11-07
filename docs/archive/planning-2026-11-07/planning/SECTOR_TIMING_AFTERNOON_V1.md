# 下午板块加减仓观察层 — Phase 1 设计（sector-timing-afternoon-v1）

> 分支：`feature/sector-timing-afternoon-v1` · 基线 tip：`afdf6c2`（当前 origin/main / 生产收据记录的固定候选）  
> 状态：研究观察层 · **actionable=false** · 预测保持 **not_calibrated** · **本阶段不部署**

## 1. 当前仓库与部署事实（2026-10-11 本机核对）

| 项 | 值 |
|---|---|
| 本机开分支前 main HEAD | `efc0898`（落后 origin/main 27） |
| 分支基线 / origin/main tip | `afdf6c2` docs: restore browser authentication deployment contract |
| 历史提及 tip `63c426a` | 仍存在；2026-10-02 R4C 合并点，已被后续 27+ 提交超越 |
| 生产 rollout 收据 | `docs/audits/MAIN_ROLLOUT_afdf6c2_20261010.md`（分支 `codex/rollout-afdf6c2-20261010`）：2026-10-10 00:32 上海切换，源码 `afdf6c2`，schema `f0e1d2c3b4a5`，健康 ok；私有 R10 / 实体手机仍 NOT_RUN |
| STATUS/HANDOFF（afdf6c2 树） | 强调 14:30 研究工作台、真实数据 UNKNOWN、actionable=false、not_calibrated；S8-F0 为关键路径；不宣称全阶段验收完成 |
| READ_MODEL_VERSION | `decision-read-v110-flow-share-provenance` |

## 2. 已有能力地图（关键模块）

| 能力 | 关键文件 | 说明 |
|---|---|---|
| 决策板五档 + 快照 | `backend/app/services/decision_board_service.py` | 档位：可加仓/可入场/可试错/观望/减仓；槽位含 14:30、14:40…15:00 |
| 主题内相对强弱 | `backend/app/utils/decision_reference.py` → `theme_relative_ranks` | 主题内 5 日收益排名，**不改五档** |
| 信号中心板块强度 | `backend/app/services/signal_center_service.py` → `_sectors` | 按 theme_l1 聚合动量/技术/宽度/新闻；研究视图 |
| 行业/概念板块快照 | `MarketService.refresh_sector_snapshots` + `SectorSnapshot` + `/sectors/market`（`BoardService.market_overview`） | AKShare 行业/概念/全市场宽度 |
| 预测 / 校准 | `forecast_service.py`、`calibration_service.py` | 快照写 `not_calibrated`；校准档案仅 candidate，**不自动**升 actionable |
| 因子研究 | `factor_analysis_service.py` | Alphalens 风格 IC/RankIC；含 Qlib 启发的 OSS 研究因子；**不进生产预测特征** |
| 份额/资金流 | `flow_share_research.py` | 研究字段，`flow_share_changes_grade=False` |
| 14:30 工作台 | `etf_1430_service.py`、`deploy/systemd/etf-1430-decision.*` | 既有工作台与定时器 |
| 开源借鉴清单 | `docs/OPEN_SOURCE_1430_RESEARCH.md` | CZSC、etf-rotation、akquant、mlforecast、MAPIE、alphalens-reloaded、ta_cn 等；**禁止整仓替换** |

## 3. 缺口（阻碍「下午板块加减仓点」清晰度）

1. **无决策板级「板块观察汇总」**：有逐标的五档 + 主题内排名 + 信号中心 sectors，但下午推送缺一份「哪些板块偏强可观察加仓 / 偏弱可观察减仓」的顶层摘要。  
2. **板块快照与 ETF 决策板未桥接**：`SectorSnapshot` 与决策板并行，14:30/14:45 未合成「行业涨跌 + ETF 档位密度」。  
3. **预测仍 not_calibrated**：走 walk-forward / Holdout 前不得宣称涨跌幅可操作；明日预测展示易误解为已校准。  
4. **读合同升版后需强制重算**：历史 v109/v110 失配会整列「数据异常」（已发生过）。  
5. **推送依赖本机在线或项目决策台**：休市/离线时只能退到公开行情旁路，口径不一致。  
6. **因子未进下午决策路径**：IC 报告与决策板隔离（正确），但缺「哪些因子值得下一阶段试点」的选型结论。

## 4. Phase 1 范围（本分支）

### 做

- 新增 **研究观察层** `sector_timing`：从决策板 rows 按 `theme_l1` 聚合档位密度与 5 日收益，给出「偏强观察 / 偏弱观察 / 中性」。  
- 挂到决策板快照 **顶层字段**（可选字段，**不升** `READ_MODEL_VERSION`，避免整板强制异常）。  
- 全程 `research_only=true`、`actionable=false`；**不**改五档、**不**改预测校准状态。  
- 设计文档 + 纯函数单测；尽量一小刀垂直切片可审。

### 不做

- 不部署、不升 actionable、不 vendor 巨型框架（Qlib/vn.py/rqalpha 整仓）。  
- 不自动交易、不接券商。  
- 不在本 Phase 完成完整预测校准或 UI 大改。

## 5. 开源/算法候选（评估，非盲目接入）

| 候选 | 许可证/形态 | 本工程建议 |
|---|---|---|
| AKShare | 已用 | 继续作为免费行业/概念快照源 |
| zhangsensen/etf-rotation-strategy | 已借鉴排名迟滞思想 | 参数变化必须重新 walk-forward；本 Phase 只做观察排名 |
| stefan-jansen/alphalens-reloaded | 模式已原生实现 | 用 IC 报告删无增量因子，不 pip 进生产路径 |
| Microsoft Qlib | 研究套件大 | **不 vendor**；只借鉴因子定义到 `OSS_RESEARCH_FACTORS` |
| CZSC | 已有对账边界 | 保持 `chan_zone_approx`；完整缠论仍为对账 |
| Nixtla/mlforecast + MAPIE | 预测/区间 | S8 校准阶段隔离研究，不得自动晋升 |
| vn.py / rqalpha / backtrader | 交易/回测框架 | 与「研究非经纪」冲突或过重；仅可作第二回测引擎评估 |
| thincat75 taxonomy（已适配 MIT） | `config/sector_taxonomy.json` | 继续用主题映射，注意当前元数据非严格 PIT |

## 6. 下一提交建议（Phase 1 之后）

1. 把 AKShare `SectorSnapshot`（industry）按名称/别名对齐到 `theme_l1`，写入 `board_pct_change` 旁证。  
2. 决策板前端/Workbuddy 增加「板块观察」窄条（强提示 research_only）。  
3. 因子：对 `return_5d/20d`、`ma_gap_*`、`oss` 因子跑既有 effectiveness 报告，挑 ICIR 稳定者进 **研究特征清单**（仍不进生产五档）。  
4. 14:30/14:45 推送改读 `sector_timing.summary`，避免只报个股。  
5. S8-F0：真实分钟权限与 walk-forward 门禁；通过前预测维持 not_calibrated。

## 7. 验收口径（本切片）

- 单测覆盖：空输入、单主题偏强/偏弱、缺失 theme、actionable 恒 false。  
- 决策板 payload 含 `sector_timing` 且不改变既有 grade。  
- 不修改 `READ_MODEL_VERSION`、不部署。

## 8. Phase 2 交付（本机夜间，未部署）

### 8.1 Bot / 例程字段路径（强制约定）

从决策板 API 读取板块观察摘要（研究向，不可操作）：

`
GET /api/decision-board
→ payload.sector_timing
→ payload.sector_timing.digest
→ payload.sector_timing.digest.headline
→ payload.sector_timing.digest.add_themes
→ payload.sector_timing.digest.reduce_themes
→ payload.sector_timing.summary.add_observation_themes
→ payload.sector_timing.summary.reduce_observation_themes
→ payload.sector_timing.themes[].market_corroboration
`

稳定常量：sector_timing.field_paths / digest.field_path = sector_timing.digest。
ctionable=false，calibration_status=not_calibrated；**不**升 READ_MODEL_VERSION。

### 8.2 SectorSnapshot 旁证桥接

- 构建快照时读取最新 oard_type=industry 的 SectorSnapshot（优先非 mock 源）。
- 用 config/sector_taxonomy.json（exact + keyword_rules）映射 sector_name → theme_l1。
- 映射失败则 market_corroboration.available=false / lignment=unavailable，**不编造**涨跌幅。
- 旁证只标注 supports_add|supports_reduce|mixed|unavailable，**不改五档**。

### 8.3 前端轻量条

DecisionSummary.vue 增加 data-testid="sector-timing-strip"，展示 sector_timing.digest.headline。
完整决策表 iframe 未改；大改 UI 留作后续。

### 8.4 因子短名单（研究，不进生产五档）

见 docs/planning/OPEN_SOURCE_FACTOR_SHORTLIST_SECTOR_TIMING.md。

## 9. Phase 3（本机夜间硬化，未部署）

- 补齐 `_latest_sector_market_evidence` + `_safe_sector_timing_observation`：SectorSnapshot / taxonomy 失败时写入空块，刷新不中断。
- 读路径对缺失 `sector_timing` 软补空块，不因此把五档改成「数据异常」。
- Bot 例程交接：`docs/planning/SECTOR_TIMING_DIGEST_HANDOFF.md`（例程改动由 Bot parent 执行）。
- 下一因子试点 stub：`backend/app/utils/sector_rs_vol_gate.py`（20d RS + 简单波动门控，研究向）。
