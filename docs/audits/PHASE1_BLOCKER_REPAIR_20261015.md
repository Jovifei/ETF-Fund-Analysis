# 本机优先一期阻断修复：源码与验收收据

目标：真实研究数据保留本机，网站消费有界展示对象；先修阻断、测试、网页GPT独立复审，再作可回滚部署。本轮未改真实DB、F盘配置/数据、已注册任务和生产镜像。

## 固定身份与验证

- 基线：103522c4c8d11d20b59891d5c3d0dbc0e49cefe7。
- 已验证源码：5ece78d41677cf8616fd96c136e86a209af84279；PR48，codex/phase1-blockers-20261015。后继文档提交不替代本源码验证身份。
- Python3.12.10完整pytest：2126总例，2103通过、23跳过、0失败/错误，794.402秒；.local/phase1-full-final.xml。
- 锁定Vitest4.1.11：204通过/26文件；typecheck/build通过。Node24.18满足项目最低22.18；不把它当Node22精确运行。
- Chromium真实浏览器隔离Mock：7通过/53.4秒，详情可用性与各入口图表弹窗；不当作local_bundle公网/实体手机/DPR专项。
- 隔离Mock ASGI五页面smoke、compileall、Node app.js语法、secret scan、diffcheck通过。
- 第一轮全量在交叉审核修复后中止，日志保留；不冒称该轮通过。前后RED、receiver154、R4守卫73/兼容260+4跳过、producer41和交叉70等证据分别保留.local目录。

## 修复任务与验收清单

| ID | 实现与源码验收 | 当前状态/剩余证据 |
|---|---|---|
| R1 | 新过期/未来包拒绝激活；V2完整40位source+config批准绑定；同id重试仅返回执；历史精确代单独STALE | 源码PASS；生产批准身份overlay未配置 |
| R2 | single/chunk/commit共同OS锁与同步域预算；含展示/暂存/nonce/receipt/temp峰值；重复块幂等、完整hash、崩溃恢复 | 源码PASS；实际服务器磁盘/RSS/失败回滚仍需发布验收 |
| R3 | 总览固定代、桌面和窄屏导航保留generation、详情和图表校验代及as_of；缺项不偷换latest/云库；历史/过期显式提示 | 源码PASS；公网正常用户消费与三方hash未验收 |
| R3-period | 周/月图在本机派生、可选chart_periods哈希与周期校验；云端不再重算；未发布周期/Chan/上下文历史明确不可用 | 源码PASS，不冒称所有功能都有真实数据 |
| R3-private | 私有持仓保留云DB；本代无价/身份不符不可用，禁止旧云quote凑P&L；不改账本 | 合成隔离PASS；真实账号人工验收仍独立 |
| R4 | 统一guard覆盖Task/worker/queue/直接领域写服务/CLI/scheduler/云模型；私有用户事务保留；board审计例外默认关且有界 | 源码PASS；见R4_CLOUD_WRITE_GUARD_20261015.md |
| R4-health | display-only仅保留单行运维heartbeat，研究不入队/claim；nonce崩溃后OS锁自动释放 | 合成真实DB健康检查/子进程崩溃PASS；不等于全库零写 |
| R5 | 运行前干净固定SHA+配置+universe+marker/DB；必需partial阻断；outbox原子写；无配置不扩大范围 | 源码PASS；原文件/失败收据保留 |
| R5-admission | 逐接口采集/存储/展示权利、时间/单位/复权证据门控；UNKNOWN不外传；compute-only分离本地权限 | 门禁源码PASS；实际证据RESOURCE_BLOCKED，不能填写虚假VERIFIED |
| R6 | 必填身份回执精确校验；空输入/缺consumer不能总PASS；真实会话/结算/截止/同批复权证据不足为PENDING/UNKNOWN | 源码PASS；真实consumer目前NOT_RUN，报告保持INCOMPLETE |
| R7 | 活锁不按age抢；任务注册默认预览、拒同名覆盖、固定SHA、注册禁用，不改系统时区 | 合成/语法PASS；未替换实际旧任务，完整job ledger/漏slot恢复仍需真实调度专项 |
| D | 完整后端/前端/构建/静态与交叉复审 | 本地PASS，精确GitHub CI另核，不继承作者数字 |
| Web | 普通基金决策Chat实读固定GitHub源码复审 | PENDING；原Chat模型错误，未产生通过结论，不创建Cloud Work |
| E | 新一致备份、不可变镜像、健康/资源/版本核对、回滚 | NOT_DEPLOYED；必须Web/CI及资源前置通过 |
| F/G | 正常网页同代、全部云研究INSERT/UPDATE/bytes退休、至少两个真实交易日scope/slots | NOT_VERIFIED，不由scheduler=false或两次手动替代 |

## 实际现场（只读）

2026-10-15现网ETF API/worker健康，源码标签103522c，镜像219eadc5a7f8；local_bundle、scheduler=false、public_composite、mock fallback=false。服务器根盘剩余约1.4GiB（97%已用），内存约763MiB available；不得凭测试绿直接传大镜像或删其他项目资产。新备份/传输/载入/保留回滚峰值必须先核算。

F盘现用live.json仅检查非秘密准入结构，universe34、provider_admission对象缺失；未读取producer_auth或.env。真实源权利/单位/时点资料需补齐后才允许新版导出；这是资源资格门槛，不由Owner同意代码执行替代上游许可。

本机到网页连接身份未确认，不重启/覆盖其他项目连接。网页复审按Jovi原授权只读GitHub，原会话Model not found已验证，尝试同项目普通Chat接力；无独立实读意见就不签发WEB_REVIEW_APPROVED。

## 下一实际动作

取得固定源码独立网页复审与精确CI；先修任何新增阻断。并行收集实际源准入与资源证据。通过后最小配置overlay/新备份/镜像切换，保留账号持仓与现网provider/LLM设置；失败回滚。真实调度、双交易日、长期soak、PIT/OOS和实体手机分别留痕，UNKNOWN/actionable=false/not_calibrated不晋升。
