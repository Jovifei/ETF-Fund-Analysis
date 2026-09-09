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
