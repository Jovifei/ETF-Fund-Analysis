# v1.0.4 增量接手

当前功能分支基于main 57470ea，见docs/versions/V1.0.4.md、docs/USER_GUIDE_V104.md和docs/LOCAL_ACCEPTANCE_V104.md。先核对固定SHA与CI，再加载原私有配置/原库副本。不删除以下历史记录，不把分支实现当生产已升级。模型API默认关闭，启用必须初始化独立密钥和本人确认费用。

## 2026-09-10 本地接收与持久部署

- 固定接收 `910e77fc866f123e0d18103048243513e3edb666` 已在独立 clone 验证基线 `57470eabcad35a6038574e893e7245f0d1adb387` 为祖先；原工程脏区未触碰。
- 远端固定 SHA 的 `workspace-ci` 成功，`public-data-v104-observation` 成功；完整 `ci` 的旧 JS 合同测试失败已在本地复现并由 `b8112d4` 修复，未合并 main、未推送审核修复、未部署服务器。
- 本地持久副本 URL 为 `http://127.0.0.1:8082`，运行 v1.0.4 / `akshare` / 数据库认证；目录实际为 ETF 1,658、LOF 382，行业 90、概念 614、全市场 1。
- 两只 ETF 各 1,197 根日线至 2026-09-09；有限准备任务选择 10 只、实际写入 137 根；报价任务因上游不可用保持失败/partial，不提升实时或 actionable 资格。
- 新闻任务实际写入 200 条 `akshare:eastmoney`；publication 使用市场时区、fetched 使用 UTC；缺失/未来时间显示待核实。完整收据见 `docs/LOCAL_ACCEPTANCE_RECEIPT_V104_20260910.md`。
- 本地副本重启前后 schema、目录、目标 ETF bars、板块统计和 integrity 均一致；Docker daemon 不可用，临时 PostgreSQL/镜像 build/container smoke 未宣称通过。
- 2026-09-10 12:58 再次执行两只 ETF 的 `quotes` 重试仍为 `TaskExecutionError/partial`；本地最新日线为 2026-09-09，今天日线尚未形成且当前公共报价能力不可用。

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
