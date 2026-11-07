# 14:30 / 14:45 板块观察 Digest 交接（Bot 例程更新用）

> 分支：`feature/sector-timing-afternoon-v1` · PR [#43](https://github.com/Jovifei/ETF-Fund-Analysis/pull/43)
> 状态：研究观察层 · **actionable=false** · **calibration_status=not_calibrated** · **本文件不改 Cursor routines**（例程在 Bot parent 侧；此处只给字段路径与文案约定）

## 1. 例程应读的 API 字段路径（强制）

```
GET /api/decision-board
  -> payload.sector_timing
  -> payload.sector_timing.digest.headline
  -> payload.sector_timing.digest.add_themes
  -> payload.sector_timing.digest.reduce_themes
  -> payload.sector_timing.summary.add_observation_themes   # 备用
  -> payload.sector_timing.summary.reduce_observation_themes
  -> payload.sector_timing.themes[].market_corroboration     # 可选旁证
```

代码常量（`backend/app/utils/sector_timing.py`）：

| 常量 | 值 |
|---|---|
| `DIGEST_FIELD_PATH` | `sector_timing.digest` |
| `SUMMARY_FIELD_PATH` | `sector_timing.summary` |
| `API_READ_PATH` | `GET /api/decision-board -> payload.sector_timing` |

## 2. 推送文案建议（中文简报）

优先用一行 headline，或直接贴 `digest.headline`（可含市涨跌旁证后缀）。

硬性口径：

- 写「观察 / 关注」，不要写成下单指令。
- 始终带 research_only / actionable=false / not_calibrated。
- `sector_timing` 缺失或为空时：说「板块观察摘要暂不可用」，不要把整板标成数据异常；个股五档以决策板 rows 为准。

## 3. 软失败行为（工程已落地）

- 构建快照时 SectorSnapshot / taxonomy 失败 -> 写入空的 schema-stable `sector_timing`，刷新不中断。
- 读旧快照缺 `sector_timing` -> API 侧补空块，不改写 grade 为「数据异常」（版本失配仍按原读合同处理，与本字段无关）。
- 「数据异常」整列只应来自 `read_model_version` / `config_hash` 失配，而不是 sector_timing 缺席。

## 4. 给 Bot parent 的例程更新清单（请人工改 routines）

本仓库不能直接改 Cursor / Grok Bot 定时例程。请 parent 在 14:30 与 14:45 例程中：

1. 登录后请求 `GET /api/decision-board`（本机 18081 优先；否则线上需只读账号）。
2. 若 `payload.sector_timing.digest` 存在：用 `headline` + `add_themes` / `reduce_themes` 写板块段。
3. 若缺失：明确写「板块观察摘要暂不可用」，再退回公开行情旁路（并标注非项目决策台）。
4. 个股加减仓观察仍可引用五档 rows；板块段与个股段分开，避免混成单一「信号」。

## 5. 相关文件

- 设计：`docs/planning/SECTOR_TIMING_AFTERNOON_V1.md` 第 8-9 节
- 实现：`backend/app/utils/sector_timing.py`、`decision_board_service._safe_sector_timing_observation`
- 前端窄条：`frontend/src/lib/decisionSummary.ts` -> `sectorTimingDigest`
- 因子下一刀：`docs/planning/OPEN_SOURCE_FACTOR_SHORTLIST_SECTOR_TIMING.md`、`backend/app/utils/sector_rs_vol_gate.py`（研究 stub）
