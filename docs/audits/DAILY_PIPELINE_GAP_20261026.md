# 每日数据—决策—网站—邮件链路排查（2026-10-26）

检查时间：北京时间 22:38–23:01。范围为只读诊断；没有修改业务代码、生产配置、定时任务或业务数据，没有补发邮件或重跑采集。此次仅新增排查报告、证据摘要和任务记录。

## 结论

目标链路没有完整交付。当前已存在并实际运行的是「本机定时采集 → 确定性研究计算 → 展示包 → 签名 HTTPS → 网站」。今天其中 5 批成功，但收盘链路失败，网站停在盘中旧批次。自动 AI 解释和邮件不在这个 dispatcher 中；历史邮件由 `mail.grokbot.com` 投递，对应任务的实现和当前运行位置尚未取得；目前没有同一份可核查的运行台账。不能再把网站部署成功、任务退出 0 或旧邮件存在，当成整个日常服务已经完成。

这也纠正此前状态说明的不足：发布收据只证明当时版本与一次接收；两交易日自然运行、日终完整更新和定时邮件仍未验收。

## 当前基线与真实路径

- 当前 E 根 main：`7b3a5757b9e0cc140e904b67bcbeb31c1eb3830b`；旧 C 工作树仍是 `f487288`，未用旧版本覆盖其他 Agent。
- 网站健康：v1.0.12，三服务镜像 `1863c32d5eae…`；研究源 `local_bundle`，云端 scheduler、LLM、analysis 均关闭。
- 实际 Windows 主任务：`ETF-Local-Live-Compute`，隐藏执行器 `pythonw.exe`；工作目录 `E:\worktrees\etf-v1-0-7-dcffa8e`，运行 `scripts/run_local_compute.py dispatch`，固定源码 `dcffa8ebac1027d174b213915ff78a7e51b99097`，private/closed-session 参数均已携带。
- 本地研究库：`F:\ETF_Data\ETF-Fund-Analysis\db\research.sqlite3`。
- 调度台账：`F:\ETF_Data\ETF-Fund-Analysis\state\schedule.sqlite3`（slots / attempts / jobs）。
- 本地展示包及回执：`F:\ETF_Data\ETF-Fund-Analysis\outbox`。
- 上传：HTTPS `/api/shadow/sync`；服务器展示目录 `/app/.local/display-cadence-3d1ab16`，由 `LocalDisplayReader` 按批准身份读取。
- 邮件：历史已投递邮件头确认发件服务域 `mail.grokbot.com`；当前仓库和以上 Python dispatcher 未实现 SMTP。对应任务当前启停、执行异常及投递日志尚未取得，不能推断它已被删除、被禁用或投递失败的具体原因。

## 今天到底做了什么

| 环节 | 当天证据 | 结果 |
|---|---|---|
| Windows 调度 | 主任务最后 18:20:20 退出 0；实际触发器含 11:38 起 20 分钟及 13:50 起 4 小时 30 分钟 | 今天确实运行，且覆盖 17:40；不是没有启动定时器 |
| 槽位 | 12 槽中 5 DELIVERED、2 FAILED_DELIVERY、1 SUPERSEDED、4 最后 MISSED | Windows 最后一次空轮询退出 0 掩盖了此前业务失败 |
| 日线 | 本机 68,996 行；10-26 当日日线 34/34，最后写入 17:48:33 | 今天已拉到收盘日线，数据还在本机 |
| 决策 | 最后本机 board 15:04:01；指标/预测最后一次完整更新在 13:58 左右 | 没有完成收盘后重算 |
| 网站 | 默认 34 行，generation `1792997752011`；14:54:58 生成，15:01:58 accepted，16:54:58 到期 | 仍在读今天盘中包，包内日线是 10-23，目前明确 stale |
| 对账 | 16:30 退出 1；实际生成 INCOMPLETE 报告，5 MATCHED / 2 RECEIPT_MISSING，消费证明 NOT_RUN | 不是邮件任务，也不代表从未运行 |
| 邮件 | 已连接 Gmail，按北京时间当天的 Unix 边界查全邮箱（含垃圾箱）ETF/基金/决策主题，0 封 | 未发现今天的相应邮件；仅限该邮箱和查询范围 |

网站时间需要区分：14:54 的包使用 10-23 已结算日线和 10-26 14:54 盘中报价，不能把日线日期当成包完全没更新，也不能把包生成时间当成当日收盘数据。服务器默认 Reader 的身份匹配且有 34 行，此次不是身份不匹配造成的空白。过期包仍可历史读取，不能通过重封旧内容把它说成今天收盘结果。

### 槽位明细（北京时间）

| 槽位 | 实际结果 / 服务器接收 |
|---|---|
| 11:40 | DELIVERED，11:48:38 accepted |
| 13:55 | DELIVERED，14:05:51 accepted |
| 14:20 | DELIVERED，14:28:17 accepted |
| 14:30 | 已出包，初次及两次重试未形成回执，FAILED_DELIVERY |
| 14:45 | DELIVERED，14:53:47 accepted |
| 14:50 | DELIVERED，15:01:58 accepted，目前网站使用这一批 |
| 14:55 | 被较新 15:00 槽替代，SUPERSEDED |
| 15:00 | 已出包，无接收回执，FAILED_DELIVERY |
| 15:15 | 两次日线覆盖 1/34、0/34；失败后过补跑窗，MISSED |
| 16:10 | 两次日线覆盖 3/34、6/34；失败后 MISSED |
| 16:40 | 两次日线覆盖 17/34、20/34；失败后 MISSED |
| 17:40 | 两次日线均 34/34；随后报价 partial 阻断，最后 MISSED |

MISSED 是台账的最终状态，并不表示从没尝试：后四槽各有两次失败尝试。

## 已定位的断点

### 1. 收盘链依赖过窄的报价合同，挡住已齐的当日日线

17:40 和 17:45 的日线均完整，但 refresh_quotes 返回 34 条，全部是非实时报价，原 TaskRun 为 partial。闭市研究虽然开启，现有 `_closed_session_quote_result` 仍要求每条 source_time 在同日 15:00–16:00。

此次最新批次有 10 条时间为 16:29:00–16:29:45，必然被该窗口拒绝。其他报价时点为 15:00 起，整批覆盖完整仍不能通过。管线随即在 quotes 后停止，没有进入新的指标、预测、信号、board 和导出。

代码：`backend/app/workspace/local_compute.py:390`（闭市证据）、`:439`（时间窗）、`:729`（必需步骤失败停止）；导出另有第二道报价合同，`:1143` 起。不能仅在 compute 层忽略 partial；也不能把 16:29 的上游时间直接认定为交易所收盘时刻、修改实时标志或把窗口一律放宽。

### 2. 快槽耗时接近 / 超过 8 分钟行情窗口，旧包重试无法成功

14:30 与 15:00 包各约 16.3 MB。14:30 决策 14:30:59 生成，直到 14:38:20 才记录 upload_1；15:00 槽的决策 15:04:01 生成，15:10:21 才进入 upload_1。导出和重复校验已经消耗了大部分报价有效时间。

对原不可变包在原始时点执行只读校验：14:30 初次 upload 起点尚合法，12 秒后的结束点已过龄；两次重试均拒绝。15:00 的初次起点和两次重试均已过龄。实际重试台账为 ValueError；`load_pending_bundle` 另明确拒绝超过 8 分钟的快照。

服务器 API 当天日志只有上述 5 个成功 POST 200，没有这两批失败请求。首次异常原因未持久化，故不能宣称第一次一定是网络故障或服务器拒绝；现有证据已证明过龄重放不能救回旧包，首次根因还需补上阶段耗时及净化错误码才可完全闭环。

代码：`scripts/run_local_compute.py:191`、`:230`、`:269`；`backend/app/workspace/local_compute.py:909`、`:923`；`backend/app/workspace/local_dispatch.py:88`、`:121`。

### 3. 邮件和 AI 没有接入这条运行链

本地 `local_settings` 明确关闭 LLM/analysis/日报，任务列表只有确定性行情和研究计算；ReportService 只生成 HTML，不发邮件。云端 local_bundle worker 只做心跳，不代替本机拉数、AI或发信。这里的 scheduler=false 是本机优先架构边界，直接打开它会复活云端研究采集，不是正确修复。

Gmail 历史确认：10-22 有 14:30/14:45 邮件；10-23 有多封晚间补发，最后检索到的邮件 Date 时点为 19:20:35（已在邮箱找到该邮件，不能把 Date 等同最终到达时间）。其发件服务为 `mail.grokbot.com`。本机非系统 Windows 任务、当前 Codex automation、etfdeploy 用户 crontab 和系统 timer 中未发现 ETF 发信入口；仓库外发送器当前状态仍未观察。因此只能确认两套链尚未统一验收，不能把无邮件全部归因于行情失败。

代码：`backend/app/workspace/local_compute.py:491`、`:676`；`backend/app/workspace/worker.py:321`、`:394`；合同：`docs/INTRADAY_REFRESH_CADENCE.md:26`，`docs/USER_GUIDE.md:14`。AI可解释冻结的确定性结果，但不能替代指标、仓位和回测计算。

### 4. 失败可见性不足

任务使用隐藏启动，符合不弹窗要求，但初次失败原因只打印到 stdout，持久台账只留 delivery_not_acknowledged / ValueError。调度器稍后没有到期槽时正常退出 0，用户看不到当天已有失败。16:30 对账也不含已批准的消费者读回。缺少「今天收盘研究未发布 / 邮件未投递」的独立状态通知和每日验收收据。

## 修复方向与顺序（此次未实施）

1. **先恢复收盘研究发布。** 先写本次 16:29 报价的失败夹具；新增明确的「同日已结算日线研究」输入合同，从完整、日期/来源/质量/复权口径可核的当日日线计算指标、预测、信号、board。新增输入语义应升级相关合同/版本，绑定新固定 SHA 验证。贯穿 mode → lineage → export，报价保留原时间与 stale/non-realtime，不借旧闭市 quote proof 绕过检查。缺数据、未来输入、错时区、范围或 hash 不符的负例继续阻断；资格维持 UNKNOWN/actionable=false/not_calibrated。
2. **修复快槽时延和重试原因。** 先持久记录 validate_base、计算、详情/图表投影、canonical/hash、写盘、发送前校验、HTTP/回执的耗时与净化 reason code。复用同一冻结 base/input hash 的不变投影，减少重复重算；以实际临界快槽耗时验证改善。保留 8 分钟原 source_time 门槛，不改 generated_at 延寿；过龄时下一槽重取报价，不能无限重传已过龄包。
3. **给 AI/邮件确立唯一运行归属。** 先取得 `mail.grokbot.com` 对应外部任务的当前计划与今天执行收据，核是否仍启用、调用哪个数据入口，避免建第二套重复发送器。随后将其接入本地持久任务或由项目维护的投递适配器：冻结 session/slot/bundle/hash，AI只解释同批研究结果；成功、无新数据、网页接收失败、AI失败均产生明确状态。邮件设去重键、有限重试、投递标识及时间，失败通知不能依赖成功分支。
4. **端到端验收后再称完成。** 以一个新固定 SHA 同时验证本地新日线 → 新指标/预测/board → 新展示包 → accepted → 网页 GET 同 generation → 邮件同批内容与投递记录。Owner收件箱、垃圾箱和正常登录页面分别核实；再验两个真实交易日及自然调度，不能用手动补发替代日常稳定运行。

现有触发器已覆盖晚槽，无需先改频率或把任务改为可见窗口。本机任务仍依赖电脑开机、用户登录和网络；WakeToRun=false，超过 20 分钟补跑窗口会遗漏。这是需明确记录的运行条件，不是今天 17:40 失败的直接原因。

## 报告依据与边界

- SQLite 均 URI mode=ro + PRAGMA query_only=ON；只查询聚合和任务状态。
- 生产调用同一个 LocalDisplayReader，只输出非敏感身份、时点和行数；未运行 Provider。
- Windows 任务只读白名单字段；API日志仅输出同步路由/时间/HTTP状态；未输出凭据或原始日志。
- Gmail 仅检索/读取已有邮件。当天按 Unix 边界 `1792944000–1793030400` 避免日期搜索时区误差。
- 机器可读证据见 [DAILY_PIPELINE_EVIDENCE_20261026.json](DAILY_PIPELINE_EVIDENCE_20261026.json)。固定旧包的过龄检查是只读复现，不是新代码测试通过或新发布验收。
- 当前 Hub revision 查询连接被拒（WinError10061）；未声称上报成功，未自动重试。
