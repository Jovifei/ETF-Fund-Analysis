# R4B 箱体与支撑压力验收（2026-09-27）

## 结论

R4B 已在隔离分支完成本地实现和验收。实现产生可回放、带时点和输入身份的日线结构研究；它不改变 canonical decision 的评分公式或阈值，箱体和结构只用于研究展示，`actionable=false`。代码已分三批本地提交；截至本收据写作时，尚未推送、合并 main 或部署。

真实行情资格仍为 **UNKNOWN**。测试全部使用隔离 SQLite/Mock/合成 K 线，没有读取或写入生产数据库，也没有请求真实 Provider 或模型。

## 身份

| 项目 | SHA / 版本 |
|---|---|
| 基线提交 / tree | `4d8fa1a4b7c5fc8dc3d0066c74dc86cd9092df18` / `6400437180c62052936f443f423910fd2a841ac6` |
| 接收分支 | `codex/r4b-price-structure` |
| 证据语义提交 | `5600d92243290dffe9e7de6d6af53fea9d48bc22` |
| 结构快照提交 | `0e5759b706fde8ea4e678f28ef53b7b8d77ec3a7` |
| 图表与页面状态提交 | `8a5b575904c4cbc5a2d63e53a8521076c80904e1` |
| 最终应用 tree | `1fc3d4657dba7f9e0f0ec5d06875eaaa45c98d83` |
| 算法 / 快照 / 图表合同 | `price-structure-v1` / `support-resistance-v4-structure` / `chart-read-v1.2.0` |

没有数据库迁移。现有支撑压力快照因方法版本变化会失效，须由已有受审计刷新任务重算；GET 不抓数、不写快照，也不补算新结构。

## 实现

- 日线输入来自统一研究价格序列；XSHG 交易日缺口和非交易日 K 线会阻断箱体。复权基准、快照日期或输入哈希不匹配时，读模型隐藏结构叠加。
- 使用 Wilder ATR14（由同一 OHLC 序列计算），不再以现价百分比冒充 ATR。当前没有可信 tick-size 元数据，因此边界容差只用实测 ATR14 的 `0.30` 倍；ATR 不可用时不生成箱体或 ATR 波动参考。
- 最近 120 根日线为候选窗口；左右各 2 根确认拐点；等价相邻平台合并到最后一根，右侧两根出现后才确认。每个独立拐点只有一个 touch ID，MACD/KDJ/RSI 只保留为附属方法，不增加触碰数。
- 箱体要求上下侧各 2 次触碰、同侧至少间隔 3 根、持续不少于 20 根、区间内收盘比例至少 80%、宽度为 2–12 ATR、回归漂移不超过箱宽的 50%。失败时返回候选或明确原因，不把滚动高低通道冒充箱体。
- 生命周期包括 `candidate`、`confirmed`、`breakout_attempt`、`breakout_confirmed`、`failed_breakout`、`invalidated` 和 `expired`。确认只使用结算日线；连续两根收盘越界才确认突破；失败/相反边界失效和 60 根到期均保存带前缀输入哈希的事件身份。
- 盘中临时行情仅在 chart GET 响应中产生临时越界提示，不进入已存快照，不改变结算状态。量能缺失仍显示价格结构，并注明量能确认不可用。
- 新快照 JSON 与旧支撑压力结果并存；图表默认只开最新箱体和两级结构支撑/压力。箱体画在发生到确认、确认到有效截止两个有界区间；其它派生价位需手动开启。周/月/分钟周期明确不显示日线箱体。
- 新增 News 状态端点失败提示和重试；补充 News、Factors、Research Archive、Review 的空态/失败态页面回归。

## 验收结果

| 验收 | 结果 |
|---|---|
| 完整后端 pytest | 1269 项：1255 passed、14 skipped、0 failures、0 errors；JUnit：`E:\Claude_allow\Download\ETF_R4B_QA_20260927\full-pytest-final.xml` |
| 条件跳过 | 缺 `TEST_POSTGRES_URL`；Windows symlink 权限；Linux 备份脚本；POSIX named pipe；Unix file mode。具体用例见 JUnit |
| 前端 Vitest | 16 files / 63 passed |
| 前端 | `vue-tsc --noEmit`、Vite build 通过；仅保留既有 Login.vue 静态/动态导入提示 |
| Node / Python / 安全 | legacy Node 39/39、`node --check`、`compileall`、secret scan、`git diff --check` 通过 |
| Ruff | 新结构引擎与专属测试文件通过；对含既有压缩风格代码的完整旧文件扫描仍有存量风格诊断，未做无关格式化 |
| 普通浏览器 | 26/26；包含新箱体与页面状态用例 |
| 认证浏览器 | 5/5；使用虚构账户和临时 SQLite |
| 响应式浏览器 | 18/18；320 至 3840 宽度、短屏菜单、触摸、DPR2、方向与缩放 |

浏览器截图、trace、列表和报告保存在 `E:\Claude_allow\Download\ETF_R4B_QA_20260927`。响应式首轮有 1 个断言仍期待旧图例文案；同步为新文案后整套 18 项重跑通过。

首轮已保留的失败与环境差异：ATR 用例精确复现旧 2% 代值（1.51765 × 2% 得 `0.030353`，OHLC Wilder ATR 为 `0.041669`）；新模块第一次因模块缺失而无法导入。读取基线源码 `4d8fa1a` 并用一个同时触发 MACD/KDJ/RSI 的分形复现后，旧聚类显示 19 个 method contributions，却没有 `touch_count`；最终合同保留 method contributions 兼容字段，并以唯一 `touch_ids` 计算触碰数。ATR 无法计算用例最初错误地破坏 OHLC，修正为有效 OHLC 加超长 ATR 窗口后通过。生命周期重建夹具初次把旧触碰排除在 120 根窗口外，测试改用明确的 200 根窗口验证“终结后新 ID”，生产默认仍是 120。跨页面回归初次被更早 chart 测试遗留的临时输入污染；将该隔离测试限定在 settled snapshot 前提后通过。

首轮浏览器端口 `18082` 被已有 Docker 端口转发占用（健康响应显示另一 development/mock 服务）；没有终止该服务。Playwright 后来显式使用独立端口与 worktree `.venv`；系统 Python 初次启动因缺 `argon2` 失败，使用项目虚拟环境后测试通过。

## 未完成的发布门禁

生产镜像未构建/切换，main 未更新；真实行情覆盖与认证资格未审核。PostgreSQL 条件未运行。公开行情输入、人工样本外研究、完整总收益与缠论属于后续独立阶段。生产部署须另核对远端 SHA/CI、备份恢复和运行收据；不能用本地测试声称线上已更新。

## 生产镜像 PostgreSQL 兼容性纠正（2026-09-27）

R4B 首次发布后追加的只读线上检查发现：既有 PostgreSQL `support_resistance_snapshots.method_version` 列为 `VARCHAR(32)`，应用曾写入的标识为 37 字符。快照保存按标的 SAVEPOINT 隔离，因此健康检查可正常而每个快照写入失败。发布后检查时，活跃 `refresh_decision_board` 数与流水线 advisory lock 均为 0；快照汇总仍是 `support-resistance-v1` 125 条、`support-resistance-v2-input-mask` 280 条，尚无 R4B 方法版本行。

修复只将方法版本改为 `support-resistance-v4-structure`（31 字符），没有新增迁移或改变算法、快照结构、参数、canonical decision、预测校准及 `actionable=false`。新增列宽回归先失败（37 > 32），修复后支撑压力与快照专项 27/27 通过；修复版全量 pytest 为 1270 项，1256 passed、14 环境跳过、0 failures/errors；前端 63/63，普通/认证/响应式浏览器 26/5/18 通过，Node 39/39、typecheck、构建和 compileall 通过。

上述为修复版本地验收。**在修复版固定 SHA 的 CI 镜像、备份副本演练、生产切换和受审计刷新任务完成前，不宣称 R4B 生产快照已恢复。**真实行情资格仍 UNKNOWN。生产部署收据与后续任务执行结果将在门禁完成后补充。

## Final independent acceptance addendum — 2026-09-28

The earlier R4B implementation and test totals above are preserved as historical producer evidence. Later independent review findings were resolved through the C1 → C2C.2 chain and the final candidate below; no earlier receipt was deleted or rewritten.

### Accepted local candidate

- Application SHA: `43bfbf6929a70f520c216b759edbaa433e920e91`
- Application tree: `12d217af3edbe34c67bc36e75b4395ab4917b001`
- Candidate Alembic head: `g8b9c0d1e2f3`
- Final full pytest: 1279 tests, 0 failures, 0 errors, 15 condition skips.
- Compileall, Node syntax, relevant Ruff, secret scan and diff check: PASS.
- Isolated PostgreSQL 16 migration and revision roundtrip: PASS.
- Final receipt: [R4B final acceptance](audits/R4B_FINAL_ACCEPTANCE_20260928.md).

### Current boundary

`R4B=ACCEPTED_LOCAL`; `M0_TECHNICAL_GATE=PASS`; `M0_FINAL_STATUS=PENDING_C2D_RECONCILIATION`. The accepted candidate has not been merged into the deployed production identity. Production remains SHA `0dbd3fee58a3f5e080aacbcd8eae8d5964aec54f`, tree `f8607b3de8decde6065ccc559c5c26b0262b8e6b`, Alembic `e609200001`. Real-data qualification remains `UNKNOWN`, canonical action is unchanged, and `actionable=false`.

### Independent review result

The remote review closed the application gates for replay/window, basis identity, immutable revisions, PostgreSQL migration/roundtrip, and final full regression. C2D documentation reconciliation is the next stage; R4C remains closed until C2D is independently reviewed.
