# 生产发布与结构因子落地收据（2026-11-10）

## 一、发布与元数据概要

- **发布时间**：2026-11-10 01:50~02:15 (UTC+8)
- **代码版本**：`98ba055f6e5be99ff949e62822b9714c7ec1894c`
- **代码分支**：`codex/sector-drawer-v1-20261108`（基于 main `3ce3a74` 独立 worktree）
- **配置哈希**：`9efe8845e2e26406de22b30b08d0697f3c52b979f6d3e06b7a1398bcca21285b`
- **生产镜像**：`china-fund-decision:deploy-98ba055`（Image ID: `2cb3e62e52a0`, 918MB）
- **生产服务**：`etf-deploy-98ba055-api-1` (healthy), `worker-1` (healthy), `scheduler-1` (running)
- **数据库状态**：Alembic 迁移 Head 保持 `b7c8d9e0f1a2`（零迁移，无 schema drift）
- **切流前备份**：`/opt/china-fund-decision/backups/fund_pre_98ba055_cutover_20261110_013325.dump`（424MB, sha256 校验通过，TOC 478 项）
- **回滚准备**：旧容器 `etf-deploy-0e2f888` 完整保留并处于 stop 状态，镜像 `china-fund-decision:deploy-0e2f888` 保留，支持秒级回滚。无关容器（jourvolt, medbox, star-photo 等）未经任何改动。

---

## 二、2026-11-09 真实行情与五期限预测重算

1. **真实行情补取**：
   - 抓取时间：2026-11-10 01:05 (UTC+8) 收盘后清算补算，不伪造盘中快照。
   - 数据源：`akshare:em:v101`，存储于 `F:\ETF_Data\ETF-Fund-Analysis\db\research.sqlite3`。
   - 标的覆盖：34/34 只宇宙 ETF 100% 覆盖，OHLC 逻辑校验（low <= min(open, close), high >= max(open, close)）、成交量（股/手单位）和价格无 NaN/Inf。
2. **结构因子与技术指标计算**：
   - 全量计算 34/34 只标的技术指标（MACD, KDJ, RSI, TD, MA, Volume）。
   - 落地三项结构因子：
     - **威科夫结构**（Wyckoff）：严格基于无前视的局部区间与量价 proxy（accumulation / distribution / neutral），标注置信度与 OHLCV 代理免责声明。
     - **道氏趋势**（Dow）：严格基于分形高低点确认逻辑（uptrend / downtrend / rally_in_downtrend / sideways），标注滞后确认（lag_n=2）与置信度。
     - **ATR 波动风险**：严格执行 `atr_pct_fixed_v1` 四档风险规则（low <1%, mid 1%~2%, high 2%~3.5%, extreme >=3.5%），小数比率口径无 100 倍偏差。
3. **五期限预测重算**：
   - 期限覆盖：1, 3, 7, 20, 60 交易日。
   - 全量计算 34 只标的全部 5 个期限，严格无前视，状态标记为 `not_calibrated`，研究专用。

---

## 三、展示包生成与公网签名同步

1. **生成与校验**：
   - 本机通过 `ROW_FIELDS_V2` 及 `compact_row` 校验，成功保留 `structure_v1` 与 `structure_shadow`。
   - 导出 Canonical Display Bundle（16,489,834 字节）。
2. **生产同步回执**：
   - 批次 Sequence：`1794246476660`
   - Bundle ID：`4d12c49f8b98067be573ecc87eaa494a3650b715622685a847d9177d47ededa2`
   - Manifest Hash：`4d12c49f8b98067be573ecc87eaa494a3650b715622685a847d9177d47ededa2`
   - 状态：`accepted`
   - 接收时间：`2026-11-09T17:50:29.778487+00:00`
   - 本地回执文件：`F:\ETF_Data\ETF-Fund-Analysis\outbox\bundle_1794246476660.receipt.json`
3. **身份登记更新**：
   - 服务器及代码库中 `config/bundle_identity_registry.json` 已登记 `98ba055f...` / `9efe8845...` 组合为被批准的有效生产者。

---

## 四、生产 API 与前端展示全量验证

1. **生产内部 Reader 验证**：
   - `latest.json` 成功指向 `bundle_1794246476660_4d12c49f8b98067b.json`。
   - 5 个期限（1, 3, 7, 20, 60）Overview 行数均为 34，`structure_v1` 覆盖率 34/34（100%）。
   - Detail 数据 34 只 ETF 全部具备，`decision.structure_v1` 字段完整。
2. **认证 HTTP API 验证**：
   - `GET /api/workspace/overview?horizon=1` -> 200 OK（34 行，34/34 包含 structure_v1）。
   - `GET /api/workspace/overview?horizon=3` -> 200 OK（34 行，34/34 包含 structure_v1）。
   - `GET /api/workspace/overview?horizon=7` -> 200 OK（34 行，34/34 包含 structure_v1）。
   - `GET /api/workspace/overview?horizon=20` -> 200 OK（34 行，34/34 包含 structure_v1）。
   - `GET /api/workspace/overview?horizon=60` -> 200 OK（34 行，34/34 包含 structure_v1）。
   - `GET /api/workspace/instruments/159819.SZ` -> 200 OK（decision 中包含 structure_v1）。
   - `GET /api/workspace/instruments/510300.SH` -> 200 OK（decision 中包含 structure_v1）。
   - `GET /api/workspace/instruments/159915.SZ` -> 200 OK（decision 中包含 structure_v1）。
   - `GET /api/workspace/sectors/representatives` -> 200 OK。
   - `GET /api/decision-board` -> 200 OK。
3. **前端呈现与向后兼容**：
   - `decision_board_workbuddy.js` & `.css`：
     - 表头扩展为 15 列，独立呈现「威科夫结构」「道氏趋势」「ATR 波动风险」。
     - 实现缺失保护，历史 bundle 缺少字段时安全回退显示「—」，不崩溃、不赋虚假分。
     - ATR 列展示波动档位（极高/高/中/低），鼠标悬停或点击展示 ATR14 及 ATR 百分比。
   - Vue 前端（`Matrix.vue`）：
     - 增加独立三列并支持 Tooltip 详细指标与规则版本提示。
     - 容器最小宽度自适应扩展至 2100px，横向滚动与窄屏表现良好。

---

## 五、本机 Windows 定时任务核验

1. **故障排查与根因**：
   - 前期退出码 `-2147024629` (`0x8007010B`) 系 `C:\Users\Admin\.codex\worktrees\etf-live-v113-a0d52e4\ETF-Fund-Analysis` 路径在 worktree 重构期间访问异常。
2. **当前状态**：
   - `\ETF-Local-Live-Compute`：触发执行成功，LastTaskResult 为 `0`（退出码 0）。
   - `\ETF-Local-Reconcile-1630`：触发执行正常启动，当前处于 `INCOMPLETE` 状态（因 2026-11-09 刚结算，未来 t1/t5 收益尚在挂起期），LastTaskResult 符合预期。

---

## 六、合规与安全边界

- 全流程未读取、未回显任何 `.env`、私钥、Token 或数据库密码。
- 系统持续保持 `UNKNOWN`、`actionable=false`、`not_calibrated`。
- 未连接任何券商接口，未启用自动交易。
