# 工程状态

更新时间：2026-08-30（板块与 14:30 工作台进展补记 2026-09-02）
发行版本：`0.7.0`

## 已实现（本地测试范围）

| 模块 | 状态 | 证据边界 |
|---|---|---|
| FastAPI API、静态看板、SSE | 已实现 | TestClient/静态资源和本地 Mock；浏览器烟测见 `tasks/todo.md` D3 review |
| SQLite、本地任务、Alembic | 已实现 | 干净 SQLite 迁移链；真实 PostgreSQL 仍是部署门槛 |
| Tushare、AKShare、Composite | 适配器已实现 | Token/权限、ECS 出口、实时字段和稳定性尚未实测 |
| 技术指标、信号、回测 | 既有基线 | 本版不改公式、阈值或策略版本；真实数据校准和第二引擎对账未完成 |
| 信号中心（读取层研究视图） | 完成 | 信号行情曲线、机会/风险/止盈前排、板块强度、可调系数、持仓命中提醒；`test_signal_center.py` 8 项 |
| ETF 信号分级（读取层研究视图） | 完成 | 第 6 页签彩色五档宽表；`GET /api/signals/grade`；现为 `signal-grade-v0.2.0` |
| 行业/概念板块目录 | 完成 | 决策看板改为东财式名称的行业+概念卡片；`GET /api/signals/boards`；只映射场内 ETF，不爬东财 |
| 预测 | 已实现基线 | 输出始终 `not_calibrated`；没有 calibrated 或收益确定性结论 |
| 新闻与多模型分析 | 合约/网关已实现 | Codex/OpenAI Responses 可作为唯一主 provider；Anthropic/DeepSeek 仅手工切换；真实端点未验证 |
| 市场上下文 | 六项注册表和任务已实现 | 默认六卡片；代理代码 null、disabled、unverified，真实资格未完成 |
| 持仓截图 OCR | 本地流程已实现 | Pillow/合约/候选确认测试通过；真实 Paddle 包/model 未资格验证，生产 Windows fail-closed |
| Docker、反向代理、ECS 脚本 | 模板/脚本已实现 | Docker/ECS/HTTPS/备份恢复需目标环境执行；镜像不含重型 Paddle |

## 运行时配置边界

- 服务器生产使用 `MARKET_PROVIDER=composite`、`ALLOW_MOCK_FALLBACK=false`。Mock、unavailable、退化或缺失核心数据都阻断 actionable 信号。
- 分析默认关闭；启用时只允许一个主 provider。Codex/OpenAI Responses 的服务器变量为 `OPENAI_API_KEY`、`ANALYSIS_PRIMARY_MODEL`、`ANALYSIS_CODEX_BASE_URL`、`ANALYSIS_PRIMARY_MODE=responses` 及对应 enabled/provider 开关。模型无工具、凭据、数值决策、数据库写入、网络抓取或券商权限。
- 市场上下文默认每 15 分钟，scheduler 每 30 秒检查任务是否到期。今日变化优先于价格，所有观察保留来源、时间、新鲜度、Mock/退化状态。
- OCR 图像默认 10MiB（`OCR_MAX_IMAGE_BYTES`）、12,000×12,000、4,000 万像素、60 秒硬超时、15 分钟 TTL。临时根 0700 私有，模型根私有只读，原图不进入普通数据库记录。云复核关闭且当前不出网。
- 发行包版本 `0.7.0` 与策略版本分离；`config/strategy.json` 当前为 `signal-v0.7.0-research` / `indicator-v0.5.1` / `similarity-corridor-v0.7.0` / `rotation-v0.5.1` / `feature-store-v0.7.0`。
- 信号中心（v0.6.0 新增）是只读取层：仅消费已落库的 SignalSnapshot/IndicatorSnapshot/新闻/持仓，信号系数只影响该视图的前排分类与曲线口径，不改写生产信号引擎的权重、阈值与状态机，因此不触发策略封版与 walk-forward 流程；独立版本号 `signal-center-v0.1.0`。
- ETF 信号分级（`signal-grade-v0.1.0`）是另一只读研究层：五档（可加仓/可入场/可试探/观望/减仓）由已落库指标快照派生，阈值只在 `config/strategy.json` 的 `signal_grade`，不碰 `signal.entry_score`。自选池已扩到行业主题 ETF + `513500.SH`/`513100.SH`/`518880.SH`/`159562.SZ`；无全市场涨跌家数时板块列显示「未验证 / 不可用」。
- **当前卡点**：无 Token 时走免费档（AKShare/东财公开 ETF），不是只能 Mock。Mock 永远 `actionable=false`，预测保持 `not_calibrated`。系统页可保存 Tushare Token 并探测连通（接口不回显）。本地 Docker（`127.0.0.1:8080`）可看 UI。下一步：免费档跑通流水线 → 可选完整档 Token → Provider 矩阵 → 再谈 ECS。
- v0.7.0 资格验证：Phase A/B 本地/Mock 已完成（commit `60da31c`）；真实 Provider、ETF 池、ECS 部署与 20 交易日影子运行待 `TUSHARE_TOKEN` 与目标环境。

## 多用户账户与持仓隔离（本地完成，尚未部署）

- 数据库账户使用 `AuthUser`/`AuthSession`：Argon2id 密码哈希、HttpOnly 会话 Cookie、CSRF、会话撤销和登录限流；浏览器不再使用 localStorage 令牌。
- 采用封闭注册：管理员通过 `auth-bootstrap-admin` 创建首个管理员，再通过 `/api/admin/users` 或 CLI 创建/停用/重新启用/重置成员；普通成员只能读共享研究并维护自己的持仓/OCR。
- 持仓、OCR 导入、报告、14:30 工作台、组合优化和 SSE 私有事件均按 `user_id` 隔离；共享信号快照不读取或持久化用户持仓。
- 旧 Bearer 仅保留非生产迁移/测试的安全共享读取兼容，不是浏览器身份，也不能访问私有报告、SSE、持仓或执行写操作。
- 生产启动强制 `AUTH_ENABLED=true`、PostgreSQL、`AUTO_CREATE_SCHEMA=false`、`AUTH_COOKIE_SECURE=true`，并拒绝旧单账户认证字段和 legacy Bearer；认证关闭仅可用于 development/test 演示。
- 多用户迁移链当前 head 为 `2c3d4e5f6a7b`；旧 NULL owner 数据需在维护窗口由 active admin 使用审计回填命令归属，未知系统报告保持 NULL。真实 PostgreSQL 迁移/备份恢复仍是部署门槛。

## 部署前必须完成

1. 在目标 Linux ECS 以真实 PostgreSQL 执行迁移、备份、隔离恢复和权限检查；生产 Windows 的 OCR 配置必须拒绝启动。
2. 分别取得 Tushare/AKShare、实时行情、新闻和 OpenAI 端点的权限/稳定性证据，不能以本地或 Mock 结果替代。
3. 为六项上下文建立 Provider 资格记录；中国/韩国半导体代理在此之前保持空代码、禁用、未验证。
4. 若需 Paddle，提供 Python 3.12 Linux wheel、模型文件和 `paddle-local-v1` manifest 的大小/SHA-256 记录；当前环境没有真实 Paddle/model 资格证明。
5. 完成真实数据 walk-forward、事件回测约束复核、预测校准和人工封版记录；在此之前预测保持 `not_calibrated`。
6. 通过 Caddy/Nginx HTTPS 反代访问，body limit 设 12MB（10MiB 图像上限加 multipart 开销），`.env` 0600，OCR transient root 0700。

## 明确不做

本项目没有自动交易、券商连接、模型自动持仓写入或投资建议。Codex/Claude Code 仅可生成异步、只读、待人工接受的审阅候选；不能把本地测试、Mock 数据、候选报告或历史快照描述为生产/实时/已校准事实。

## ETF 14:30 Workbench 覆盖包状态

- 代码：已在分支 `feat/etf-1430-workbench-complete-local` 提交并推送（本轮 `76c5f2b` → `47debe2` → `ac8baf4`）。
- 页面：`/workbench/1430`。
- API：`/api/workbench/1430/summary`、`/{ts_code}`、`/generate`。
- 预测：1/3/5/10 日相似样本研究基线，继续 `not_calibrated`。
- 支撑压力：分形、均线、布林、ATR、Fibonacci、成交密集成本、指标确认拐点、趋势线及缠论重叠区近似。
- 未完成资格：真实 5/15 分钟 point-in-time、CZSC 对账、ECS systemd、真实 Provider 和 20 日影子运行。

## 板块数据（行业 / 概念 / 全市场宽度）

`SectorSnapshot.board_type` 三分类落库，两个只读研究视图共用同一口径：

| board_type | 含义 | 数据源 | 消费视图 |
|---|---|---|---|
| `industry` | 行业板块涨跌家数 | AKShare（东财主源 → 同花顺备用） | K线企稳分析看板、ETF信号分级 |
| `concept` | 概念板块涨跌家数 | AKShare | K线企稳分析看板、ETF信号分级 |
| `market` | 全市场（全 A）涨跌家数 | AKShare（Sina `stock_zh_a_spot` 主源 → 腾讯 `qt.gtimg.cn` 回退） | K线企稳分析看板、ETF信号分级 |

- 主题 → 板块名 走 `config/etf_1430_workbench.json` 的 `sector_alias` / `concept_alias` **精确映射**，不做模糊匹配；`broad_market_themes`（宽基 / 创业板 / 科创50）命中者改取全市场宽度。未登记主题显示「—」，**不用无关板块兜底**（避免把无关板块的涨跌家数显示在标的旁误导判断）。
- 健壮性：`_market_breadth` 用 `case` 排序让真实源（`source != "mock-sector"`）恒优先，仅当不存在任何真实源时才回退 mock；返回值带 `source` / `is_mock` 供前端标注演示态，防止 mock 假数据遮蔽真实研究结论（对应 `47debe2`）。
- ETF信号分级（`signal-grade-v0.2.0`，只读研究视图）此前 sector 列恒为「未验证 / 不可用」：根因是旧实现按「池内同主题 ETF 互比」计算，而自选池每个行业主题仅 1 只 ETF，恒不满足「≥2 只」条件。已改为复用 K线企稳分析看板的同一套真实板块查询（`ac8baf4`），两视图口径一致，且前端 `app.js` 仅消费 `sector.label` / `sector.note`，字段结构保持兼容、前端零改动。
- 本地实测（2026-09-02，9 只标的，live HTTP 200）：4 只宽基 ETF 显示全市场 3094 涨 / 1995 跌（源 `akshare`）；5 只行业 ETF 显示真实行业板块（半导体 21/165、军工装备 49/33、医药 45/210、电池 39/67、黄金 8/47）。
- 门禁：全量 `pytest` 退出 0、0 失败、1 skip；`python -m compileall -q backend/app` 与 `node --check` 均通过。
- 本地预览：`AUTH_ENABLED=false` 下 http://127.0.0.1:8000 （仅本地预览；真实 ECS / PostgreSQL / HTTPS 部署仍为部署门槛）。
- 免费数据源现状：AkShare 已集成（板块、全市场宽度、ETF 基础数据）；Baostock、通达信 mootdx 未集成。盘中实时 tick / 分钟线 AkShare 不可得，若需补该能力须另行接入 mootdx 或 Tushare 实时档，属独立增强项。


## 集成：板块数据与 K 线企稳看板

- 已合入行业/概念/全市场三类 `SectorSnapshot`、AKShare 真实宽度优先、K 线企稳看板与 `refresh_sector_snapshots`。
- 多用户认证与持仓隔离继续作为基础安全边界；板块数据属于共享市场数据。
- Alembic 单链：`... -> f7a8b9c0d1e2 -> 0a9b1c2d3e4f -> 1b2c3d4e5f6a -> 2c3d4e5f6a7b -> e7f8a9b0c1d2 -> f1a2b3c4d5e6`。
