# 本机优先一期发布与验收收据

本文件汇总源码、实际部署、既有Windows任务及签名公网交付证据。区分本地演练、实际正式运行、服务进程读取与正常认证浏览器；不把短窗或单次运行当作所有长期/资格门槛完成。

## 固定身份

| 项目 | 已核身份/结果 |
|---|---|
| main源码 | 9fe9fe87adbc216f2db5d77248f990a48e79abad；本地main已快进、干净 |
| tree | 7f3214f94aba8d113cd3e532d21f2a20867d50ef |
| 策略config | 972a045a66349166210f0378530164a1a2d50e9a72b26309bf17437bf2258305 |
| schema | f0e1d2c3b4a5，未修改 |
| 运行镜像（v4脚本切换） | sha256:93d4e2956d7fc8302886787705cf10fa82dec6bd99cf4725da7c6b3d62d69862；398项发布哈希核验PASS；由219基镜像离线构建 |
| 当前生产 | 已由旧103522c切到固定9fe/source+tree+镜像一致；实际运行配置绑定核验PASS |
| 新备份 | PostgreSQL与本机SQLite新一致备份完整性/哈希核验PASS；私有路径、库内容和凭据不写入本文件 |

展示批准config绑定本机生产者972a...；云端原调度参数导致load_strategy散列为ebbd3b9d9c61efd320089b2c25621aae334947021adcf9704ef043b6db1babf2。已核原始策略文件与非intervals部分完全相同，未改公式/阈值，也未为散列相同而覆盖云端调度配置。

## 最终验证

- Python3.12最终完整pytest：2264总例，2241通过、23跳过、0失败/错误，809.282秒；原始XML `.local/phase1-final-wire-20261016/.local/frozen-9fe-full.xml`。该XML计数已独立读取，不能继承为后继业务源码结果。
- 受影响104项通过；锁定Vue205项、类型检查/生产构建通过。前端构建33文件逐项哈希一致，构建清单SHA256 `157777170289e60e7efe19d79661e0be61eab7563fc9d0be1e54cfa60f84a206`。
- 7组精确预合并CI全绿，包括[CI 38775107179](https://github.com/Jovifei/ETF-Fund-Analysis/actions/runs/38775107179)、[CI 38775114025](https://github.com/Jovifei/ETF-Fund-Analysis/actions/runs/38775114025)；同提交其余通过运行：workspace-ci push38775107011/PR38775113618、audit-platforms push38775106711/PR38775113632、postdeploy-ci PR38775113780。
- 既有1d6739a真实Chrome隔离Mock两文件7项通过，41.1秒；其前端源码与最终9fe相同，不冒称9fe后端重新执行该轮Mock测试。另有最终9fe本地真实包消费验证，均不等于公网验收。
- 本地真实Bundle正常页面QA PASS，来源见下。所有RED、早期失败与已过时收据保留；Jovi明确免除本轮网页GPT复审，本地工程复审通过，不冒称WEB_REVIEW_APPROVED。

## 修复任务与验收清单

| ID | 已交付实现与源码结果 | 运行/资格边界 |
|---|---|---|
| R1 新代准入 | 接收器v2.3；实际UTC拒过期/未来激活，完整批准source/config精确绑定；同ID仅幂等回执，历史精确代STALE读取。PASS | 生产批准身份与新包一致，实际签名公网accepted；历史STALE不冒当前资格 |
| R2 有界同步 | single/chunk/commit共同OS锁，64MiB域含nonce/staging/receipt/temp及发布峰值；不可变块、完整hash、重试回执、保护current/previous；滚动GC仅旧有效缓存。PASS | 暂存也无空间则拒，不扩大预算；实际域预算/运行资源PASS；v3失败回滚已发生且旧版健康，不能将失败记PASS |
| R3 同代消费 | 总览、桌面/窄屏导航、详情/图表generation+as_of绑定；缺项不偷换云库/latest；过期明确显示；主动读取最新；周/月本机生成，私有账本保留。PASS | 本地真实包消费PASS；正常公网认证用户、DPR/不等价口径/手机独立 |
| R4 云研究退休 | 统一guard覆盖worker/queue/Task/领域写服务/CLI/scheduler；研究例外默认关；保留私有事务和单行运维heartbeat。PASS | 不表示全库零写；研究INSERT/UPDATE/bytes至少两交易日待观测 |
| R5 本机执行 | 固定清洁SHA、配置/universe/marker/专用DB；partial不冒成功；原子outbox。显式私人研究保留UNKNOWN，DENIED/EXPIRED及付费源边界不放开。PASS | 不是上游许可或生产数据认证；正式canonical F根实际任务已执行；上游资格仍UNKNOWN |
| R6 对账 | 完整精确V2回执、缺消费者不能总PASS；时点/结算/同批复权证据不足保持PENDING/UNKNOWN。PASS | 实际签名HTTPS回执及API容器内只读验证进程同代/hash已核；普通认证网页NOT_RUN，本地QA不替代 |
| R7 调度 | OS锁/崩溃释放；注册默认预览/禁用、固定SHA、拒同名覆盖，不改时区。PASS | 旧任务定义已备份且仅Action迁移，手动运行LastResult0；自然触发尚待验收；统一slot台账和漏slot恢复尚未交付 |
| R8 闭市研究 | v1.1.1精确phase原因；>=16当前verified交易日stale，<09上一verified交易日date-not-today；09–16/周末不放行，capture不可跨午夜；同DB/TaskRun/完整报价hash/实际选择绑定。PASS | 保留原partial和非实时/未核时间；不制造结算或实时资格 |
| R9 有界恢复 | 仅private已有免费Composite同code/date最多再读一次；明确限流/权限/schema/预算拒绝；逐次audit随Task事务提交，原partial/数量门槛保留。PASS | opaque ProviderError不证明暂时网络故障；不重抓成功批次，不拼源 |
| R10 目标scope | 34目标写入/coverage与52背景计算分离；RPS、横截面、市场门控/组合背景不缩；目标hash不冒global；空/未知/重复/停用目标拒。PASS | 不删除/停用18只；内部board背景与正式导出34分别记录 |
| R11 无损编码 | projection v1.1/safe-integral-json-v1；仅有限safe整数float转JSON整数，负零/bool/非整/非有限/超范围不动；重新hash，字段/bars/universe/16MiB不变。PASS | 字节hash变化必须新代新回执，不能复用旧身份 |

## 实际真实Bundle与本机消费者

历史独立演练来源必须分开：真实抓取 `ab84f3eba62ce23c8ae4b11e98e0e06134bded5e`；真实派生 `9dd54bb6c3d2035048d9e9e440095fc2dada0669`；本次实际export-only `9fe9fe87adbc216f2db5d77248f990a48e79abad`。此节不冒称9fe重新抓取的完整定时任务；最新正式完整9fe链路见下一节。

- generation `1792084218689`；bundle ID `698ed5eb6d51a8d31362462218af9d159353461d6c6b3290cb0f183aaba3b419`。
- canonical 16,647,811字节；SHA256 `22bd914790e97f82784a32b03adec1329fd0fd427277e4a2868f4e71c9c80967`；本机publisher实际落盘完全一致。
- overview/details/charts/chart_periods各34；34条报价unverified、is_realtime=true为0、timestamp_verified=true为0，holding非空为0。每只周/月部分齐全，该次演练的市场上下文和板块明确unavailable；不沿用为后续正式运行状态。
- owner_private_research、source/license UNKNOWN、research_only=true、actionable=false、not_calibrated保持。真实原始/研究价格不等价时不合格叠加隐藏，不宣称支撑压力已取得可靠资格。
- 127.0.0.1:18093独立展示存储/空账户SQLite，真实Chrome正常总览→详情→图表同代/as_of、弹窗开关、主动latest、390窄屏无横溢。浏览器无写操作/外域请求。测试服务已核身份后停止。
- 原始 `.local/phase1-final-wire-20261016/.local/real-bundle-qa-9fe9fe8-20261016/qa-summary.json` SHA256 `aa1f2ee6e660103cc209d5edc59f8281d23d9fab2c88bef0c3acb27f24035b54`；`evidence-index.json` SHA256 `2fdd808be7ea8da334f4bbe31592fb2817c13403635ae7b15b4f41ca19b6b0f7`。PNG/raw JSON仅留本机，去敏身份与hash可回传。
- 额外精确shadow bundle端点因无当前用户返回401；未绕过认证，初始失败记录保留。正常公网登录/实体手机/DPR2/真正不等价价格专项均NOT_RUN。

## 最新正式运行：全部9fe，而非旧演练重放

已有Windows任务在原Principal、8个triggers及Settings不变的条件下，仅迁移Action到Python3.12/固定9fe/canonical F数据根，并由执行者手动启动，LastResult=0。实际8阶段均执行：bars/indicators/forecasts/signals的34目标完整，board输出完成，板块采集成功；quote collector仍partial并通过完整typed closed-session proof接受，市场上下文6/7 optional partial导出unavailable。没有将两项partial改成collector succeeded。

- 本次实际抓取、派生、导出source均为`9fe9fe87adbc216f2db5d77248f990a48e79abad`，使用原canonical本机数据根，非clone替代。
- generation `1792087932590`；bundle ID `15e28b4f3a14b7ef1825e60bdbe24f23279c62e57814e11939b011b1e3a4d6e4`。
- canonical 16,664,353字节；SHA256 `a85a666cffeb7852d2004c22732eb91af6ea36b2e46c0df2f08cb50825aa7205`，实际接收对象同hash。
- manifest生成上海2026-10-16 02:11:58，过期04:11:58；签名HTTPS receipt accepted于02:13:42。非实时输入对应2026-10-15闭市，资格UNKNOWN/actionable=false/not_calibrated未变。
- 生产API容器内独立只读验证进程5次直接Reader读取核generation/as_of/hash/周期/安全flag，禁止DB/network/subprocess调用计数均0。该项是服务进程验证，不冒正常认证浏览器路径。
- 公网health200、新JS与发布资产匹配；匿名浏览器正常跳转登录，未读取用户账号或绕过登录。
- 同步域33,312,706字节<67,108,864；API/worker健康，scheduler稳定，无OOM、重启0。独立Reader验证进程峰值RSS 209,604,608字节；5次最大4.5345秒只是顺序进程调用，不是HTTP p95或SLO达标。
- 14张研究表01:50:05–02:16:44短窗：exact与INSERT/UPDATE/DELETE、heap/total bytes差分全零。不公布私有行数或库路径，不推断两交易日无增长。
- 新一致PostgreSQL与本机SQLite备份已核完整性/哈希；schema f0e1d2c3b4a5未改，未直接修改生产研究/用户数据库内容。旧原始数据和回滚资产保留；根盘约1.13GB（十进制，约1.05GiB）剩余，容量并未解决。

实际去敏收据（单独留存，不能带入私有原配置或数据库）为`actual-task-delivery-9fe.json`、`actual-task-step-summary-9fe.json`、`signed-delivery-1792087932590-independent-checks.receipt.json`、`runtime-binding-comparison-9fe.json`、`task-migration-preservation-9fe.json`。上述5份已由文档整理者实际读取所需公开身份/状态并与父Agent现场报告核对，不冒称整理者执行了部署/备份/正式任务。独立下载比对的signed-delivery收据SHA256为`3b8c6ed912056d32ba6fceafd2f083e1da9916c18ff23c0798011ada94313a9a`。

失败证据保留：v3的`--wait`把正常disabled scheduler误作失败，触发回滚并确认旧版健康；第一次本机实际尝试因父Agent计划配置误判而暂停。二者不改为PASS，最终成功以v4及新代回执为准。v4操作身份由执行父Agent保留完整哈希（SHA256 d5dcc997577be0aefb0470fff84494965e3af8e6f346ebaed77030405ca8e6a8），不与运行源码SHA混淆。

## 验收状态与下一阶段

| 阶段 | 状态 |
|---|---|
| SOURCE_TESTED / LOCAL_REAL_BUNDLE_CONSUMER_PASS | PASS，固定源码/独立演练范围如上 |
| 网页GPT审批 | OWNER_WAIVED，不等于GPT已审核通过 |
| 新一致备份/398发布哈希/不可变镜像 | PASS |
| v4生产源码/镜像/批准身份/资源/健康 | DEPLOYED；配置绑定PASS，旧失败回滚证据保留 |
| 正式canonical F根、owned固定SHA任务迁移 | PASS，原Principal/8triggers/Settings保持 |
| 真实完整CLI→签名HTTPS accepted新代 | PASS；通过手动启动真实已有任务，Ready/LastResult0；下一计划14:20:20，未冒自然触发 |
| 生产API容器内只读验证进程Reader同代/时点/hash | PASS；不是正常HTTP认证用户浏览器验收 |
| 普通认证用户/私有持仓人工验收 | NOT_RUN；匿名登录边界PASS |
| 14研究表零变化 | SHORT_WINDOW_PASS；两真实交易日PENDING |
| 自然触发/各slot | PENDING；统一slot台账/补漏尚未交付 |
| 7–14日soak/手机/DPR2/标签叠字/真正不等价价格专项 | PENDING；普通截图和本机窄屏不替代 |
| 权限/许可/PIT/OOS/校准与策略晋升 | UNKNOWN / NOT_RUN，不自动交易 |
| Hub | NOT_SENT（Win10061），不作为本次已完成部署的阻断或虚构已上报 |

下一优先级先解决约6分38秒任务与最密5分钟slots的容量协调、完整job ledger及漏slot恢复，继而观察自然触发和两个真实交易日；先于新增因子。价格口径/数量/时点与数据源资格保持原门槛，不能为缩时或补槽调低。

生产保留AUTH_ENABLED=true、原持久DATABASE_URL、AUTO_CREATE_SCHEMA=false、AUTH_COOKIE_SECURE=true及原provider/mock/LLM配置；账号/持仓不迁入展示包。首次安装仍按auth-bootstrap-admin契约，已有浏览器账号不重建。后继文档提交只记录收据，不替代运行源码验证身份。

机器可读摘要：[PHASE1_RELEASE_20261016.json](PHASE1_RELEASE_20261016.json)。源码身份绑定9fe9fe8，后继收据提交仅文档。
