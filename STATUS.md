# 当前项目状态

## 2026-10-22 00:40（北京时间）远端只读核验更正

PR [#49](https://github.com/Jovifei/ETF-Fund-Analysis/pull/49) 已于 2026-10-16 22:53:53（北京时间）合并；本次读取的 main 与 codex/cadence-recovery-20261016 均为 `3d1ab1696653403cab2f6942495a1abc0e8c5dfb`，源码树为 `bd59fa1acc2ca50e9564e8f40e0109a77e0c86e2`。下文“独立分支验收”“最终全量/精确 CI 未结束”等描述是合并前历史状态，不代表当前远端仍未合并。

本次通过 GitHub API 核实该精确 SHA 的 push 工作流 [ci 38919500214](https://github.com/Jovifei/ETF-Fund-Analysis/actions/runs/38919500214)、[workspace-ci 38919500521](https://github.com/Jovifei/ETF-Fund-Analysis/actions/runs/38919500521)、[audit-platforms 38919500609](https://github.com/Jovifei/ETF-Fund-Analysis/actions/runs/38919500609) 均为 completed/success；PR 工作流 [postdeploy-ci 38913010857](https://github.com/Jovifei/ETF-Fund-Analysis/actions/runs/38913010857) 亦为 completed/success。这是远端 CI 状态核验，不是本轮重跑测试。PR 描述中的 2460 PASS / 24 SKIP 为原执行者报告，不冒充本轮独立测试结果。

源码合并和 CI 成功不证明生产已切换、上传已恢复或真实页面已消费。下文固定 9fe 发布是历史部署回执，当前生产身份、本机自然触发、两个真实交易日、上传回执、正常登录/持仓及手机验收仍须最新现场证据；本次未确认这些门槛通过。保留原数据、备份、失败记录及 UNKNOWN / actionable=false / not_calibrated 边界，不授权清理、扩容或部署。

## 以下为原阶段记录（保留历史证据）

2026-10-16调度候选正在独立分支验收：持久slot/job台账、漏跑恢复、同包重传、尾盘快路径已实现；Jovi最新要求已恢复网页GPT规划/复审，前一发布的临时免审不延续。网页复审及真实采集发现的执行身份、报价控制覆盖合同已补闭环回归；报价专用延后降级接口优化保持旧选择规则，最终时效待实测。最终全量/精确CI/复审未结束；生产仍为下列9fe固定发布，正式Windows任务未切。禁用原生探针迁移与保存XML四节恢复已通过，不等于正式自然触发或两个交易日通过。

个人ETF/LOF研究工作台：真实历史与确定性计算保留本机，网站消费有界展示包，账号与持仓事务保留云端。不自动交易，未校准预测不是操作依据。

2026-10-16发布已完成：PR48合入main，源码`9fe9fe87adbc216f2db5d77248f990a48e79abad`、tree `7f3214f94aba8d113cd3e532d21f2a20867d50ef`；根目录main已快进且干净。v4生产镜像`sha256:93d4e2956d7fc8302886787705cf10fa82dec6bd99cf4725da7c6b3d62d69862`已生效，schema f0e1d2c3b4a5未变。后继文档提交不替代此源码验证身份。

- 最终完整后端2241通过、23跳过、0失败/错误（809.282秒）；聚焦104通过；Vue205/类型/构建通过，7组精确预合并CI绿。
- 本地真实34只Bundle正常页面消费QA通过；本轮网页GPT复审由Jovi明确免除，工程复审由本地完成，不冒称GPT已审。
- 已有Windows任务保留原Principal、8个triggers和Settings，仅迁移Action到Python3.12/固定源码/canonical F根。手动启动该真实任务，8阶段执行，LastResult=0；任务Ready、下一计划14:20:20尚未自然触发验收，实际新采集、派生、导出均为9fe；02:13:42（上海）签名HTTPS accepted generation `1792087932590`。
- 新代34只包已在生产API容器内只读验证进程只读Reader核同代/时点/hash；公网health200及新JS匹配。匿名浏览器仍跳转登录，未绕过认证。正常认证用户页面尚未验收。

数据边界保持：34报价原始collector partial由精确闭市typed proof接受，只作2026-10-15收盘非实时研究；source/license UNKNOWN、actionable=false、not_calibrated。市场上下文6/7的optional partial明确unavailable；板块采集本次成功。不能说8阶段全部collector succeeded。

14张研究表短窗（01:50:05–02:16:44）exact与INSERT/UPDATE/DELETE、heap/total bytes差分全零，不等于两交易日通过。同步域33,312,706字节<64MiB，服务健康、scheduler稳定、无OOM/重启0。5次进程内Reader最大4.5345秒不是HTTP p95或SLO；云盘仍约1.13GB（十进制，约1.05GiB），旧原始数据保留，容量问题未解决。

下一优先级是6分38秒左右任务与最密5分钟slots的容量/频次协调、完整job ledger与漏slot恢复，先于因子扩展。自然定时触发、两个真实交易日、7–14日soak、正常登录/持仓人工验收、本人手机/DPR/标签叠字/真正不等价价格口径专项及PIT/OOS/许可资格分别待验收。Hub仍NOT_SENT（Win10061），不作为已完成部署的否定，也不伪造上报成功。

详见docs/audits/PHASE1_RELEASE_20261016.md。私有配置、DB/持仓、旧失败与回滚资产保留，不能清理未知资料。
