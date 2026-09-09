# P0–P4 代码交付与验收矩阵

日期：2026-09-06；交付形态：完整源码 + 预构建 Vue 静态资源 + 测试证据 + 截图。
工作站版本 `0.9.0-rc.2`，应用包 `0.8.0`，策略 `signal-v0.7.1-research`。两者不可混写。

## 来源与范围

最后重新读取的 GitHub main 为 `3c7bdc7ff36b3dea482651e087127a33c4974903`。
吸收 PR #28 开发头 `7adfbc0d6dd38edc8345b67705ae86aa1d6acd4e`；恢复结果与其 Git tree
`1e3471e525ce50baec3615ced1f9fb3062f84fa0` 完全一致，然后继续修改与测试。
此前会话说“未产生任何代码/提交”不准确；保留已存在开发成果，不重复推倒。
本包包含恢复后的修复与新增内容，**不是该远端提交的原样归档，也不是当前 main 已发布版本**。本次不写远端，由用户提交。

## 分阶段结果

| 阶段 | 已有可执行交付 | 主要实现 | 实测证据与边界 |
|---|---|---|---|
| P0 | 合并后的 planning-v2、需求 U01–U12、安全/迁移合同、历史原文归档 | `docs/planning/WORKSPACE_PLANNING_V2.md`、本页、文档索引 | 当前实现/历史规划/待验资格分开；全部基线文件离线保留 |
| P1A | Vue 三态侧栏、全局搜索、账户/个人设置、移动抽屉、统一 ChartAdapter | `frontend/src/`、`workspace/ui.py`、`workspace/chart.py` | TS/build、19 个 Vue 测试；真实组件浏览器测试；生产 HTTP 浏览器测试仍需复跑 |
| P1B | 固定 Vibe commit 的隔离 install/doctor/verify 工具、原生产物导出适配、独立 CI | `scripts/vibe_trial.py`、`bridge/export_vibe.py` | **工具与适配已交付，真实模型试点未通过验收**；当前 Node 不满足上游最低版本，未登录模型，历史隔离试验有上游测试失败 |
| P2 | 总览→搜索四动作→统一详情→自选→持仓 CSV/XLSX/手工/OCR候选→确认/修订/撤销→成本线 | `workspace/read_model.py`、`imports.py`、`import_revisions.py`、Vue views | 后端用户隔离/导入/图表对账、离线浏览器实际确认和成本线；真实中文 OCR 引擎未安装，失败可手工录入 |
| P3 | 固定证据任务导出、严格结果导入、人审；原生 Vibe 包预览/未验证候选；设备配对/签名/租约/撤销；低频任务 | `jobs.py`、`external_research.py`、`bridge_api.py`、`worker.py`、`bridge/etf_agent_bridge.py` | ASGI 真实认证多用户/CSRF/防重放/失效/幂等测试；无真实模型、无实际远端 HTTPS 传输验收；日报/Bridge 默认关闭 |
| P4 | 小规模因子诊断、逐日 pairwise Spearman、样本计数、Rank IC/ICIR/分组收益/换手、持仓权重与主题/相关性、3 个有来源的风格模板 | `factor_diagnostics.py`、`config/research_styles.json`、Factors/持仓页 | 诊断与展示可执行；40 个名字不等于40个独立有效因子；未做候选收益认证，不自动入生产策略 |

P0/P1A/P2/P3/P4 的基础代码路径已形成可运行产品，不只是空壳或按钮原型；但没有把所有长期扩展项和真实部署验证都标成完成。
P1B 的最终标准“真实、可解释的上游模型研究产物”**尚未满足**：本包补齐的是受控运行与真实产物进入网站的代码通路。

## 本轮新修复，不只是重新压缩旧分支

### 数据写入与读取

`MarketService.refresh_daily_bars` 从逐根 SELECT 改为按标的批量读已有记录；真实回归样例中，100 根 bar 原实现触发103次 SELECT，新实现上限5次，与 bar 数量不再线性增长。
增加整批输入校验、重复冲突拒绝、savepoint 隔离、相同 quality_hash 跳过写入、修订真实更新。
新增 `ingestion_policy=daily-batch-v1`；不改指标公式、信号权重或预测模型。此改善针对数据库操作，**不是对公网行情下载速度的倍数承诺**。

API 搜索/总览/快照采用有界批量只读查询；GET 不触发行情抓取、模型或回测。重计算入 worker 队列。
worker 保留 partial/skipped/failed，不把上游少数成功改写为全部成功。0、负数、非有限价格显示 invalid，不用于估值。

### 前端竞态与图表

身份切换增加 epoch 和请求序号：即使旧响应在 JSON 解析后才完成，也不得写回新用户状态；旧401不得退出新会话。
退出清理私有缓存和未完成请求；服务器偏好恢复、键盘焦点、移动抽屉和减少动效均有实现。
KLineCharts 只投影已有服务端 MA/MACD/KDJ/RSI 序列；MA30 补齐。主图使用当前 S/R 区域和已录入成本，不让多个文本标签堆叠挡住 K 线。
预测 1/3/5/10 独立呈现，不拼进真实 OHLC；未验证分钟线不叠日线指标。S/R 来自已确认日线快照，可能与最新报价不同步，已显示提示。

### Vibe 原生导入

新 `bridge/export_vibe.py` 仅选5类原生文件，不复制 `.local`/认证目录。
网站先预览，确认不含个人隐私后建立 **external_unverified 待审核候选**，保留原文件 SHA256 与版本。
不假装外部公司报告执行了本网站此前的冻结 ETF 任务；不把 Markdown 自动变成可信事实。
哈希证明内容完整性，不证明作者、模型身份或投资结论。

## 开源吸收的实际边界

Kairo：原创信息布局与暗色单强调色，不复制素材/源码。KLineCharts：Apache 依赖作渲染，独立算法不接管指标。
Vibe：独立固定版本运行与产物适配，不接本项目数据库。TradingAgents：反证与风险视角，不引入完整交易运行依赖。
QuantDinger：任务分层参考，未复制受独立许可证约束的前端。tick：展示参考，无源码复制。
DSHQuant：候选/验证/去重方法，人物模板与研究资产分开；不采信宣传收益。KHQuant：未来独立回测对照，当前未内嵌。
现有 Qlib/Alphalens 风格研究代码和可选依赖保留，但不会自动安装所有重量级模型。

## 尚未完成/需要真实环境验收的内容

真实 Vibe/Codex 完整研究与 ETF 专属扩展采集；真实中文 OCR、生产 PostgreSQL 和 Docker、行情 Provider 凭据及覆盖率；标准 HTTP/TLS/CSP 浏览器全链路。
个人组合基准 beta/穿透成分重叠/机构持仓等不应从现有权重和收益相关性推断为已经实现。
真实5/15分钟 PIT、14:30后可成交性、费用滑点、purged OOS、校准、前瞻 Shadow 与人工研究资格批准仍属于 Q 线。
股票公司财务/公告/公司行为是 S2。券商、自动交易、LLM修改指标/持仓/当前动作均不在本包范围。

## 回滚

关闭 `WORKSPACE_UI_ENABLED` 可恢复原界面；不删除旧HTML/JS。新专属 URL 在关闭开关时不保证对应旧页存在。
Bridge/日报关闭独立开关，停止 worker 后已保存研究和导入审计保留。
生产回滚先备份，不能对有数据的新表直接执行破坏性 downgrade；详见部署页。
