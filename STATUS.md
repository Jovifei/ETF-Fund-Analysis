# 2026-09-10 本地交接包（V105第一阶段工作稿，尚未发布）

## v105 当前公网状态（2026-09-11）

- 公网 `https://etf.joviluma.com` 当前运行量能修复提交 `208858e` 的独立源目录 `deploy-v105-208858e`；API、worker healthy，scheduler running，公网 health 返回 production、`public_composite`、认证开启。
- 切换前 PostgreSQL 备份为 `fund_decision_20260911_084351.sql.gz`，精确回滚 Compose 和 v1.0.4 源目录均保留。账户、持仓和自选只读计数保持 `3/0/6`。
- 当前服务器时刻尚未进入盘中报价窗口；两只 ETF 日线与报价沿用最新已完成交易日和待核实公开快照，scheduler 将在交易时段按既有节奏刷新。完整记录见 `docs/PRODUCTION_DEPLOYMENT_RECEIPT_V105_20260911.md`。
- 当前运行源码目录为 `deploy-v105-406cad0`（缓存修复提交 `406cad0`）；22:25 维护重算已修复新浪回退成交量丢失：35 个启用标的 `akshare:sina:v102`、缺量 0，指标 35/35 到 2026-09-11，决策板 `数据异常=0`。夜间整体 stale 仅因 15:01 公开报价超过时效且实时资格未通过；legacy 看板已固定 no-store，登录后不会复用旧快照。

## v105 当前本地接收结果（2026-09-11）

- ZIP 校验、`verify_bundle.py`、固定基线 `46c713d4` 和补丁清单均通过；独立分支为 `codex/v105-handoff-local-20260910`。
- 包内第一阶段与 R1/R2/R3 必要修复已分小提交完成；完整后端、Vue、旧 JS、普通/认证浏览器通过。Node 24 与目标 Node 22 的版本差异、专用 PostgreSQL/Docker 条件未完成。
- v105 本地真实副本 URL 为 `http://127.0.0.1:8084`。目录 1,658 ETF / 382 LOF；两只 ETF 各 1,198 根日线至 2026-09-10；三指数真实 OHLC 缓存为上证/沪深300 1,198、 中证全指 799。
- 中证全指市场上下文仍旧缺口，Sina 成交量、实时资格、因子/预测资格继续阻断；SQLite scheduler 与 worker 并发写入出现 `database is locked`，已停止本地 scheduler 并保留证据。
- 完整本地收据见 `docs/LOCAL_ACCEPTANCE_RECEIPT_V105_20260911.md`；生产收据见 `docs/PRODUCTION_DEPLOYMENT_RECEIPT_V105_20260911.md`；本轮未合并 `main`、未改标签。

本包基线为 `46c713d4a7f6f247461ec9b075948f25c6741df7`；新增内容用补丁与文件SHA256绑定。应用包版本仍为1.0.4；本地接收证据与生产部署证据分别记录，不相互替代。

先读 `docs/HANDOFF_V105_LOCAL_PACKAGE.md`。待补齐原表重复展示、图表虚线/全屏实测、AI交互、真实数据与Windows部署验收；不能沿用旧报告声明这些通过。平衡刷新默认关闭。以下历史记录原样保留，生产状态必须重新现场核对。

---

# v1.0.4 增量接手

当前功能分支基于main 57470ea，见docs/versions/V1.0.4.md、docs/USER_GUIDE_V104.md和docs/LOCAL_ACCEPTANCE_V104.md。先核对固定SHA与CI，再加载原私有配置/原库副本。不删除以下历史记录，不把分支实现当生产已升级。模型API默认关闭，启用必须初始化独立密钥和本人确认费用。

## 2026-09-10 公网生产状态（当前）

- 公网 `https://etf.joviluma.com` 已运行提交 `3e4b9fa` 对应的 v1.0.4；API 与 worker healthy，scheduler running，公网 health 返回 `version=1.0.4`、`provider=public_composite`、认证开启。
- 本轮数据刷新修复把 AKShare bounded timeout 从 20 秒提高到 60 秒。scheduler 的全量 `refresh_quotes` 已成功写入 35 个启用标的，并在 14:35、14:40、14:45 连续复核成功；`510300.SH`、`512480.SH` 最新检查时均有 2026-09-10 14:45 左右报价，按未完成实时资格契约标为非实时/待核实。
- 受审计补历史任务使两只 ETF 各 1,197 根日线到 2026-09-09；三只指数缓存各 1,197 根 OHLC 到 2026-09-09。成交量缺失、实时资格和研究因子门禁保持原状态。
- 生产 PostgreSQL 备份、旧 v1.0.4 源目录、旧镜像和回滚 Compose 均保留。完整记录见 `docs/PRODUCTION_DEPLOYMENT_RECEIPT_V104_20260910.md`。

旧段落中的“未部署服务器”是部署前的历史记录，以本节为当前事实源；本轮未合并 `main`。

## 2026-09-10 本地接收与持久部署

- 固定接收 `910e77fc866f123e0d18103048243513e3edb666` 已在独立 clone 验证基线 `57470eabcad35a6038574e893e7245f0d1adb387` 为祖先；原工程脏区未触碰。
- 远端固定 SHA 的 `workspace-ci` 成功，`public-data-v104-observation` 成功；完整 `ci` 的旧 JS 合同测试失败已在本地复现并由 `b8112d4` 修复，未合并 main、未推送审核修复、未部署服务器。
- 本地持久副本 URL 为 `http://127.0.0.1:8082`，运行 v1.0.4 / `akshare` / 数据库认证；目录实际为 ETF 1,658、LOF 382，行业 90、概念 614、全市场 1。
- 两只 ETF 各 1,197 根日线至 2026-09-09；有限准备任务选择 10 只、实际写入 137 根；报价任务因上游不可用保持失败/partial，不提升实时或 actionable 资格。
- 新闻任务实际写入 200 条 `akshare:eastmoney`；publication 使用市场时区、fetched 使用 UTC；缺失/未来时间显示待核实。完整收据见 `docs/LOCAL_ACCEPTANCE_RECEIPT_V104_20260910.md`。
- 本地副本重启前后 schema、目录、目标 ETF bars、板块统计和 integrity 均一致；Docker daemon 不可用，临时 PostgreSQL/镜像 build/container smoke 未宣称通过。
- 2026-09-10 12:58 再次执行两只 ETF 的 `quotes` 重试仍为 `TaskExecutionError/partial`；本地最新日线为 2026-09-09，今天日线尚未形成且当前公共报价能力不可用。
- 生产修复后，本机 8082 的外部 live env 已同步为 60 秒并重启；14:54–14:55 对两只 ETF 的受审计报价重试返回 2/2，旧失败记录保留为历史证据。

# 当前开发：v1.0.3 历史与研究入口修复

## 2026-09-09 部署状态

- 服务器已运行审核分支 `codex/v103-local-review-20260909` 的 `c60a15788d5206a407fc6d8a4238137a9ee19b80`；API/worker healthy，公网 health 返回 v1.0.3。
- 服务器保留旧镜像回滚 tag和 PostgreSQL 备份；生产仍为 `public_composite`、`ALLOW_MOCK_FALLBACK=false`、模型/OCR关闭。
- 中证全指已通过 `akshare:index:tx-v103` 补齐 1,196 根；缺量 ETF 仅展示价格指标，因子诊断保持研究态、不可操作。
- OCR v5 本地合成图已通过适配器验证；Vibe 上游 Windows 资格和真人模型仍待独立用户登录/环境门禁。

基线204a31cbc0214a6e80389224c238bc897b2279af（codex/parallel-v102-gapfix-20260908），分支fix/v103-history-research-20260909。应用/前端版本1.0.3；不得把旧main当作已包含工作站。未合并main、未移动旧标签、未执行本版生产部署。

已提交应用阶段：aabc390c历史逐标的隔离；cec11c6b指数缓存/收藏/人工复盘/因子选择/归档；4bb08a77原盘中状态兼容；0ecbad7d无凭据缓存重算与首次指数注册表。最终交付固定SHA见PR与接收Prompt，不能部署只包含传输材料的中间提交。

必须保留市场总览中的原WorkBuddy模板、唯一ETF详情、行业/概念与全目录搜索。OHLC有缓存时可显示K线与价格指标；缺量、旧单位和未校准研究不升级为操作级信号。1/3/5/10与当前动作、指标公式不变。

先读[版本](docs/versions/V1.0.3.md)→[验证](docs/VALIDATION_V103.md)→[本地接收L1–L5](docs/LOCAL_ACCEPTANCE_V103.md)→[历史存储](docs/HISTORY_STORAGE_V103.md)→[开源落点](docs/OSS_APPLIED_V103.md)。真实行情网络/权限、OCR模型、本人Codex与Vibe真实任务留待本地；API密钥安全存储、行情包可信重导入/自动双向同步、月度预测与自动参数进化尚未实现。

Schema未新增，Alembic head仍d40609090002。ETF数据契约仍cn-fund-shares-cny-v1.0.1；旧单位修复必须原有审计流程，不能直接乘系数。原账户/持仓/数据库不被初始化覆盖。

上一版生产记录已原文保留在[部署前文档](docs/archive/pre-v103/STATUS.md)，只描述2026-09-07的历史收据，不代表v1.0.3已上线。当前服务器状态必须现场核实。
