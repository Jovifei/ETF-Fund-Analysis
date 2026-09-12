# ETF 全面落地审核（2026-09-12）

## 结论与核验范围

当前系统能作为受限研究工作站运行，但尚不能宣称数据资格、自动刷新和 Codex 接入全部落地。以下是源码审查、无网络纯函数复现、GitHub 实际 CI 状态与生产只读检查；不以旧测试报告代替当前验证。本轮未修改业务代码、生产配置或数据库，未调用付费模型。

审核对象：接收分支 `33e976c85008647ca51c0dfcd458d3e66f9e55de`；生产源码挂载 `deploy-v105-406cad0`。原工程 HEAD `11fb295352246769b4f2ae9efaf07d5333bc9c44`，19 个暂存改动保留；远端 main 为 `57470eabcad35a6038574e893e7245f0d1adb387`。原工程的未发布账户/旧壳改动不等于生产代码。

01:23 生产只读检查：API/worker healthy，scheduler running。异常分组实际长度为 0；最近重建快照仍为 9 月 11 日 22:25。进程健康只证明存活。

## 必须优先修复

### P1-1 新浪单位资格判定依据不足

`backend/app/providers/akshare.py:173-188` 用 amount/volume 与 close 的 10% 偏差作为“份额/元”资格。amount/volume 是成交均价，不等于收盘价；二者同时乘 100 后比值不变，无法证明绝对单位。纯函数复现：close=1.2 时 (volume=1000,amount=1200) 与 (100000,120000) 都被接纳为 v102。

此前因六行超过 5% 而放宽到 10% 的证据，不能代替供应商单位合同或独立来源核验；“所有行不再缺量”不能解释为来源资格通过。应固定 SDK/端点版本，核对字段定义、同日独立成交量和成交额、份额拆分口径；均价落在 OHLC 内只作合理性检查。先冻结资格提升，建立验证清单后通过受审计重抓恢复，禁止直接按系数改旧库。

### P1-2 未复权价格断点进入指标与预测

`backend/app/providers/akshare.py:163-165,216-219` 固定 adjust=none；`backend/app/providers/data_contract.py:32-58` 只检查旧来源、缺量、单一价格基准和单根 OHLC，没有跨日断点或拆分/分红事件核验。`backend/app/services/indicator_service.py:64-90`、`forecast_service.py:299-330` 随后使用这些历史序列。

生产只读发现 588200.SH：2026-07-20 close=3.539，07-21 close=1.349，全部 adjust=none。这约 -61.9% 的变动会进入收益和模型；本轮没有把其原因擅自认定为拆分。必须查独立历史及公司行动，建立价格展示与复权收益序列的明确合同，并阻断未经解释的断点。

### P1-3 收盘任务与数据结算截止冲突

`backend/app/core/clock.py:40-46` 在15:01进入 AFTER_CLOSE；`backend/app/scheduler.py:299-303` 成功后12小时内不再抓；`backend/app/services/market_service.py:116-121` 在15:15之前只请求昨日数据。因此15:01任务“成功”后，15:15不会补今天。昨天生产15:01任务及随后仍截至9月10的日线已经展示此路径。

应统一结算时间，并以目标交易日覆盖成功决定完成，增加15:01、15:16、源延迟、重启和次日补漏验证。

### P1-4 失败或不完整工作被记为 succeeded

`backend/app/services/task_service.py:518` 默认 result 缺少 status 就成功；`indicator_service.py:180-188` 即使全部 skipped/failures 也不返回状态；`forecast_service.py:445-452` 同样如此。`task_service.py:210-213` 对缺部分上下文也强制 succeeded。此前35项指标全部跳过，却被记录成功，正是实际案例。

应统一定义 succeeded/partial/failed、目标记录覆盖、结果新鲜度，沿用同一状态进入 TaskRun、worker、scheduler 和页面；不能只修工作器外层显示。

### P1-5 当前远端 CI 双失败

实际查询33e976c：ci 在 Unit and integration tests 失败，workspace-ci 在 Workspace backend contracts 失败，均 exit 1。尚未取得具体失败断言，不能归因为环境或 Node 弃用警告。

- https://github.com/Jovifei/ETF-Fund-Analysis/actions/runs/34612255959
- https://github.com/Jovifei/ETF-Fund-Analysis/actions/runs/34612255965

先读取日志复现并修复，固定最终 SHA；未执行到的后续构建/浏览器步骤不得计为通过。临时 PostgreSQL 条件套件需要显式 TEST_POSTGRES_URL，不能用生产迁移代替。

### P1-6 Codex 页面引导与 runner 目录保护冲突

`frontend/src/components/AISetupGuide.vue:7-14` 在同一 PowerShell 改 HOME/USERPROFILE 后登录并执行 work；`bridge/etf_agent_bridge.py:284` 再调用 private_root(root/runner-home)，而其 `:55-57` 拒绝目录等于 Path.home()。无写入模拟已复现 `BridgeError dedicated_bridge_directory_required`。照页面执行可能尚未跑模型就被挡住。

修复方向：登录环境仅作用于 Codex 子进程，bridge 保留真实用户 HOME；或明确定义 runner 专用目录的验证，不删除安全门禁。补“照抄页面步骤”的Windows端到端回归。

## P2：稳定性与展示合同

## 补充：并行审核与父任务复核

### P1-7 14:30 actionable 存在独立门禁缺口

`backend/app/services/etf_1430_service.py:294-322,407,457` 只检查报价标记、最大年龄、钟点窗口；没有交易日判断、未来时间拒绝、历史/指标/复权资格关联。父任务无网络纯函数复现：2026-09-12（周六）14:30，quote_time 在次日且标记为verified/realtime，返回 actionable=true，同时 historical_1430_backtest=not_qualified。当前生产相应近期SignalSnapshot的actionable=true数量为0，不代表此代码路径安全。修复统一QualificationGate后再开放实时报价。

### P1-8 金额与因子缺失值仍会变成数值

`data_contract.py:41-56` 未检查amount；`indicator_service.py:73-83` 把缺失amount转0；`factor_analysis_service.py:383-417` 保留NaN后调用feature_store，而 `utils/indicators_v05.py:30`、`structure_indicators.py:75-85` 再填0，产生MFI/CMF等伪有效值。金额/量能因子的coverage不能由填补后的非空值计算。应按每个因子输入依赖保留资格mask，缺失输出null，不全面禁止价格类诊断。

### P2-7 前值与输入hash不能完整复现

`signal_grade_service.py:314-345`、`decision_board_service.py:777-791` 未限定previous与current的版本/config/schema一致；`indicator_service.py:87-91`只hash尾400根但计算全历史，`forecast_service.py:356-364`只hash600根。改更早数据可能改变结果但hash不变。应绑定完整实际输入与算法配置；前值按同一公式相邻日期重算或标不可比。

### P2-8 部分校准预测混入调整

`signal_v05_service.py:67-90` 只要任一期calibrated即进入分支，却对其他期一起计分，未落实strategy.json的requires_calibrated意图。应逐期过滤或要求配置规定的全体期限均通过；当前未校准运行不证明未来混合状态正确。

### P2-9 Windows Bridge 私有目录缺ACL验证

`bridge/etf_agent_bridge.py:50-63,121-135,233-240` 在Windows只用DPAPI保护device.secret，未核验目录ACL；证据、prompt、结果明文文件可能继承宽权限。实际泄露与否取决于目标目录ACL，本轮未宣称已发生泄露。接入前用仅当前用户权限的目录并验证runner-home/jobs权限。

### P2-10 部分模型结果使失败任务延迟释放

`bridge/etf_agent_bridge.py:194-206` 只要result.json存在就尝试提交；异常时也仅在文件不存在时上报失败。模型写出无效/部分JSON会让服务端任务等待租约到期。应校验完整结果再恢复提交，非法结果显式失败且不能自动重付费。

另：模型选择目前是CLI字符格式校验，不等于费用上限；启用自动work前应把批准模型与次数/输出预算绑定任务。`docs/AI_CONNECTION_SECURITY_V104.md:34`引用bridge/bridge.py与实际etf_agent_bridge.py不一致，需同步接入文档。认证/me及其旧页面缓存覆盖需回归，但仅缺no-store不能直接判定真实浏览器已经缓存。

混合adjust时图表显式选择none可以作为价格展示设计，不能仅因选择none就判定bug；研究预测仍需明确价格基准、事件连续性与不可操作标记。本报告不把这一点直接当作已证实安全绕过。

## P2 明细（续）

1. **指数日线不会默认自动更新**：`scheduler.py:342-352` 只在 balanced 模式执行 refresh_index_history，生产 BALANCED_REFRESH_ENABLED=false。上下文点位与指数OHLC是两条存储路径。应把必需指数日线独立纳入受预算的盘后任务。
2. **SQLite 并发锁不足**：`task_service.py:70-87` 的 threading.Lock 不能保护独立 scheduler、worker 子进程；`backend/app/db/session.py:13-34` 缺完整跨进程写协调。本地已有 database is locked 证据。选定单写者或 PostgreSQL 本地方案后再宣称持久调度完成。
3. **异常计数漏键**：`decision_board_service.py:367,831` counts 仅包含五档，排除数据异常。读取该键后 coalesce为0会制造假通过。应增加异常计数并断言各组总数等于 rows；本轮直接量取 groups['数据异常'] 长度，当前为0。
4. **均线箭头混用两种语义**：`backend/app/utils/indicator_state.py:97-104` 有前值时比均线斜率，无前值时比价格位置；图例却只说价格在均线上/下。固定语义并显示依据日期，不能以同一箭头切换解释。
5. **旧壳刷新失败不能结束等待**：`backend/app/static/app.js:362-384` 主要靠新snapshot_id清除pending，后端快照无其期待的refresh_state。任务失败/worker离线时需按task_id展示终态并允许重试。
6. **发布产物证据分叉**：原工程、remote main、接收分支、生产源码挂载与旧运行时镜像不同。应提供单一release manifest，绑定源码SHA、依赖锁、前端产物hash、镜像digest、迁移head；工作区脏改动逐项审核，不能直接合并覆盖。

## Codex 实际接入顺序与验收门槛

当前生产 `WORKSPACE_BRIDGE_ENABLED=false`，桥接尚未开通。桥接只接受 `codex-cli 0.149.0`（`bridge/etf_agent_bridge.py:29,289-291`），并检查MCP为空、工具隔离开关；未知版本不得直接放行。doctor 明确不检查模型登录。

正确推进顺序：先修复引导目录冲突；为实际安装CLI建立固定版本隔离验证；服务端显式开启Bridge；使用本人登录的独立runner目录；页面产生一次性配对码；本机pair指向实际HTTPS生产origin；创建固定证据包；经本人费用确认执行最多一次小预算work；核对回传job_id/input_hash、证据引用、候选报告及审核状态，再验收断网、撤销、过期与重启。

模型API是另一条接入方式：仓库外主密钥、API和worker同用户同文件、允许服务地址、保存不外呼、一次费用确认和结果审核。Codex订阅不能推定第三方API免费。本轮未启用任何模型或支付测试。

## 落地执行顺序

1. 先修 CI、数据单位资格与未复权断点，形成可信样本和拒绝样本；这是可信研究输出的前置条件。
2. 修结算调度与真实任务状态，验证连续交易日收盘、失败后恢复、指数自动更新。
3. 对齐原表/详情/图表的日期、单位、前值、分组、异常计数；以登录态页面和API快照逐项比对，缓存假说不能仅凭缺响应头就宣称根因。
4. 单独验收Codex与模型API；Windows DPAPI、真人登录/配对/结果回传必须现场成功。
5. 固定一个最终SHA与产物，临时SQLite/专用PostgreSQL/普通和认证浏览器/CI全部通过后再发布；保留原工程、账户、数据和回滚材料。

完整缠论、支付订阅、自动训练、自动云地同步、完整场外基金目录为范围外未实现能力，不应混入本轮缺陷修复承诺。
