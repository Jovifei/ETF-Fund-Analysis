# R2–R4A 本地实现与验收收据 — 2026-09-26

## 结论与身份

- **代码实现：PASS（本地隔离分支）**。从 `main` 基线 `c63f669095e6eb44e1e9c185deecf0f7af02b27c` 开始，在 `codex/r2-freshness-lifecycle` 完成盘中同读时、详情可用性和研究价格基准修复。
- 应用代码提交：`8b52d39d22ebb21a41e269ab9ce9863b85dd3b83`；该提交树：`d7ce9c857f48a99e130cf6060700974213c4e9c0`。随后只增加详情空态/禁用状态前端测试，提交 `f4286d590fd6f9565192754e40c553048286823d`，不改应用代码。
- **GitHub/main：未推送、未合并。生产部署：未执行。** 生产运行身份沿用上次收据记录，未在本阶段重新查询远端。
- **真实数据资格：UNKNOWN**。本阶段测试使用隔离 SQLite 与 Mock；没有请求生产 Provider、访问生产业务库、改写价格/量额/认证，或提升 `actionable`/预测校准。
- 没有数据库 schema 变化或 Alembic migration。图表读取合同升级为 `chart-read-v1.1.0`；决策读取版本为 `decision-read-v108-research-basis`；支撑压力算法输入口径版本为 `support-resistance-v3-research-price-basis`。

## 交付

### R2：同一读取时点

- 详情响应提供 `read_as_of`，图表读取接收该时点并回显；详情只展示与该时点相同的图表响应，避免请求乱序拼成不同代数据。
- 日线和分钟线查询都截断到 `as_of`；未来报价按旧数据显示并标记 stale，未来生成的指标、预测及决策快照不进入本次详情。
- 当前交易日未结算行由有效临时观测替换，同日仅保留一根 K；15:15 以后有正式日线时优先使用正式数据。临时层不写入 `DailyBar`。
- `input_hash`/`series_id` 绑定所用记录、周期、价格基准和指标版本；页面读取仍为 GET，不触发 Provider。

### R3：逐模块可用性与决策说明

- 详情 API 增加 instrument、price、history、price basis、indicator、volume、forecast、decision 状态及稳定原因码。已同步目录但未启用的标的仍可读已有数据，并明确标记 disabled。
- 空历史返回 `history_not_prepared`；不支持周期返回 422 `unsupported_chart_interval`；目录不存在与证券类型不支持分别返回明确 404 原因码。
- 价格、图表、指标、预测和决策分模块显示；刷新失败时保留最后成功的详情。缺决策显示“研究决策未生成”，不再使用泛化“数据异常”兜底。
- 决策说明只呈现已有 canonical grade/reason、前一份已保存快照变化、读取时点和数据限制；仍固定 `actionable=false`。

### R4A：显示价格与研究价格分离

- `ChartData.bars` 保持来源原始显示序列；新增 `research_bars` 作为指标、周/月聚合和支撑压力计算序列。公司行为研究仅作用于 `adjust=none` 的输入；已有 `qfq/hfq` 不重复套用公告拆分因子，混合 adjustment 继续阻断。
- 原始与研究价格不同的页面提供“原始行情/拆分调整研究”切换。不能映射到原始基准的指标线和支撑压力在原始图隐藏；研究图带明确基准、证据 ID、周期、输入 hash 和序列 ID。
- 周/月研究 bar 从同一研究日线聚合；原始周/月 bar 仍独立保留。成交量缺失保持 NULL；依赖量能的方法不可用时，价格结构研究仍可展示。
- 支撑压力快照方法版本及决策读模型版本更新。部署后旧版本快照将被拒绝或显示 stale，需通过现有受审计刷新链重算后再展示为当前快照。

## 验收结果

| 检查 | 结果 |
|---|---|
| 后端完整 pytest | `1250` collected，`1236 passed`、`14 skipped`、`0 failed`、`0 errors`；收据：`E:\Claude_allow\Download\ETF_NEXT_STAGE_QA_20260926\full-pytest-release2.xml` |
| 前端 Vitest | `62/62`，16 个测试文件通过 |
| Vue 类型检查 | PASS |
| Vite 生产构建 | PASS；有一条既有 Login.vue 静态/动态导入提示 |
| `compileall` / `node --check` / legacy Node | PASS；legacy Node `39/39` |
| 浏览器普通/认证/响应式 | `20/20`、`5/5`、`18/18`，均使用项目隔离 Mock SQLite；截图/trace 在 `E:\Claude_allow\Download\ETF_NEXT_STAGE_QA_20260926\playwright-ordinary-release`、`playwright-auth-release`、`playwright-responsive-release` |
| Route matrix | PASS；所有当前页面入口及直接旧路由重定向，详情/空历史/禁用标的/刷新错误状态有独立覆盖 |
| `git diff --check` | PASS |

首轮全量 pytest 曾有一项旧读模型测试失败，因为其 fixture 只返回 `bars` 而没有 `research_bars`。详情读取已兼容旧内部载荷；该用例单独复跑和最终全量均通过。首轮完整 JUnit、修复后复跑和最终 JUnit 均保存在上述证据目录。

最终 14 项 skip 是条件门禁：未配置 `TEST_POSTGRES_URL`；Windows symlink/ACL 及 POSIX named pipe/Unix file mode/Linux-only 任务在当前主机不可用。未将这些标为 PASS。

普通浏览器首轮有两项失败：实时刷新 mock 未提供 `read_as_of`；未知直接 URL 被后端精确路由规则作为 404 返回，而非 SPA catch-all。夹具已与新响应合同一致；新增 route matrix 只检查后端明确开放的 Vue 路径，并确认 `/legacy` 与 `/workbench/*` 的旧入口现在能抵达 Vue 路由重定向。最终普通浏览器 `20/20` 通过，首轮截图/trace 留在证据目录。

Ruff 检查不是本批接受门禁；仓库已有压缩式 Python 代码存在规则告警。本轮修复了新增 import 顺序、未使用变量和 `zip` 长度检查告警，没有借机格式化不相关模块。

## 后续边界

本地代码已提交到隔离分支；此收据不表示 main 已更新或生产已发布。生产部署仍需后续发布流程、固定 SHA CI 工件、备份/恢复演练以及部署后 API/worker/scheduler 和任务刷新核验。R4B 箱体/支撑压力研究、R4C 完整缠论、N1 新闻证据、R5 Bridge、R6 真实数据资格与样本外校准仍未完成。
