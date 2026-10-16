# 当前工程交接

最新授权覆盖：本轮调度补漏继续本地实现、网页GPT独立复审，通过精确测试后受控部署，再安排两个真实交易日。网页连接已恢复；已修execution_identity及真实quote返回无覆盖字段的控制合同，报价延后优化按原选择优先级并由固定旧版差分验证。旧143.103/127.816秒未达120目标，最终候选须独立实测，不继承源码复审或中断全量结果。生产9fe/正式任务未切，最终候选及测试结果以本轮后继收据为准。原生禁用探针从保存XML恢复四节一致已实测通过，原任务保持；不要把它记为自然触发。下文免网页复审仅描述前一发布，不能延续到本轮。

目标：本机真实采集/存储/确定性计算，网站仅消费有界展示结果，保留云端私有账号和持仓。Jovi已授权修复、测试和部署，并明确免除本轮网页GPT复审，由本地作工程决策；不再等待网页恢复，也不冒称网页复审通过。

PR48已合main并快进根目录。固定运行源码`9fe9fe87adbc216f2db5d77248f990a48e79abad` / tree `7f3214f94aba8d113cd3e532d21f2a20867d50ef`。最终后端2241通过/23跳过、聚焦104、Vue205/类型/构建、7组精确CI绿。本地真实包页面QA通过。经v4发布脚本切换的镜像`sha256:93d4e2956d7fc8302886787705cf10fa82dec6bd99cf4725da7c6b3d62d69862`已生效；schema f0e1d2c3b4a5保持。详见docs/audits/PHASE1_RELEASE_20261016.md。

## 本次实际交付

已有自有Windows任务的Principal、8个triggers和Settings未变，仅迁移执行Action到Python3.12/固定9fe源码/canonical F根。通过手动启动此任务完成真实8阶段、LastResult=0及签名公网HTTPS接收：上海2026-10-16 02:13:42，generation `1792087932590`，bundle `15e28b4f3a14b7ef1825e60bdbe24f23279c62e57814e11939b011b1e3a4d6e4`。本次抓取/派生/导出均9fe；此前ab84/9dd/9fe混合来源只是独立演练，不是最新生产链路。

生产API容器内只读验证进程Reader核同代/时间/hash通过，公网health200与新JS匹配；匿名浏览器正常跳转登录，未绕过认证。正常登录用户/持仓页面尚未验收。本地18093真实包QA已停，截图/hash/初始受保护端点401证据均保留。

原始quote collector partial没有改写：34条精确闭市typed proof接受2026-10-15非实时观察，UNKNOWN/actionable=false/not_calibrated不晋升。市场上下文6/7 optional partial明确unavailable；其余所需scope34完整，板块采集本次成功。

## 下一顺序

1. 当前任务耗时约6分38秒，长于最密5分钟slots。先交付频次/耗时容量协调、统一slot台账和漏slot恢复（尚未完成）；不改算法阈值，不把一次手动启动当8个自然触发槽已通过。
2. 验收自然定时触发、至少两个真实交易日的scope/slots及研究表INSERT/UPDATE/DELETE/bytes差分。现有约27分钟全零只是短窗，不能签发两日完成。
3. 补正常认证用户/私有持仓、本人手机、DPR2/标签叠字/真正不等价价格口径专项，长期soak与PIT/OOS/许可资格分别留痕。
4. 云盘仍约1.13GB（十进制，约1.05GiB），旧原始数据尚保留，另作审计迁移/保留规划；没有删除授权的资产不清理。Hub Win10061上报未发送单独记录，不篡改为已发送。

接收器v2.3拒新过期/未来及未批准code/config，历史精确代可STALE读取。用户主动“读取最新批次”才解除旧代pin。统一64MiB按临时写入峰值计费，保护current/previous，仅回收校验通过的更旧缓存；满空间保守拒绝。现同步域33,312,706字节，后续仍持续观察。

显式--private-research不等于上游许可或单位已验证。闭市例外仅在verified交易日及精确phase/source/task/DB捕获proof下运行，盘中与其他partial门槛保留。真实原始/研究价格不同且无法映射时叠加隐藏，不能宣称支撑压力、预测或策略已经可靠。

## 浏览器认证部署契约（必须保留）

- 生产保持AUTH_ENABLED=true；现有DATABASE_URL指向持久数据库，保留用户与持仓，不把本机展示库替换成账户DB。
- AUTO_CREATE_SCHEMA=false；由Alembic执行受审迁移，HTTPS保持AUTH_COOKIE_SECURE=true。
- 首次安装通过auth-bootstrap-admin创建管理员；已有部署保留原数据库用户。浏览器使用数据库账号与安全会话Cookie。
- 新一致备份及不可变镜像/回滚材料已核；失败受控回退，不做静默降级。详见docs/ALIYUN_DEPLOYMENT.md。

先核实际SHA/tree/分支/数据源及任务定义，不用旧分支标题判断版本。保护Owner修改、私有配置/DB/持仓、任务及回滚资产；不reset/clean/stash。S0–S9进度JSON仍是正式台账，生成MD/HTML不手改。后继文档HEAD不能替代固定源码测试，任务--expected-sha须对应实际工作树HEAD。
