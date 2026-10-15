# 本机优先一期阻断修复与验收

Jovi已授权实际修复、测试、网页端GPT复审，通过后可回滚部署。基线origin/main 103522c4c8d11d20b59891d5c3d0dbc0e49cefe7；独立codex/phase1-blockers-20261015，原目录/所有数据和配置保留。不调算法/阈值、不自动交易、不伪造上游许可，不删除旧数据和失败证据。

## 修复与源码验收

- [ ] R1 接收激活：过期/未来新包不切latest；批准code/config身份绑定，历史STALE与幂等重试独立。先负例，保留V1/V2及gzip回执。
- [ ] R2 传输：分块单写者、重试幂等、临时文件唯一、current/previous+staging+nonce共同预算；满盘/中断不破坏保护代。
- [ ] R3 消费：详情/图表/预测等跨请求固定generation；不存在/缺项明确不可用，无旧DB/latest偷换；原有horizon能力边界明确。
- [ ] R4 云端退休：统一阻断所有研究写入口（worker/admin/CLI/read-path），保留合法用户持仓事务与默认关闭的受审例外。
- [ ] R5 本机准入：缺配置、身份dirty、必需partial、无marker/DB均提前失败；逐接口权限/单位/时间UNKNOWN不外传，不把文档同意当上游许可。
- [ ] R6 对账：收据字段完整精确；无包/消费者未验收不能报总PASS；真实交易日、截至时间、可比价格与结算门禁，未到期保留PENDING。
- [ ] R7 调度：任务所有权、单实例/活锁和固定身份；不覆盖他人任务、不改系统时区，验收真实slots与两交易日单独保留。

## 验证与发布顺序

1. 按模块写失败回归并保留RED/GREEN；受影响pytest、完整pytest、compileall、Node语法、锁定Vue测试/typecheck/build；全部绑定最终源码SHA/tree。
2. 集中收据进GitHub；网页端普通基金决策Chat通过固定GitHub源码独立复审。连接故障不冒作PASS，不创建Cloud Work。
3. 复审通过且精确CI绿后核实际生产SHA/image/schema、磁盘/RSS、当前快照/回滚资产；新一致备份、不可变镜像、最小配置overlay，保留账号/持仓/provider与LLM设置，失败回滚。
4. 本地真实执行仅使用已准入源；缺新增权限只阻断相应动作并询问。公网回执与正常私有网页消费的generation/object hash三方对账；云研究表INSERT+UPDATE与bytes两真实交易日观察，不能由scheduler=false代替。

## 完成状态

SOURCE_TESTED、WEB_REVIEW_APPROVED、DEPLOYED、NORMAL_CONSUMER_PASS、CLOUD_WRITES_RETIRED、TWO_TRADE_DAY_PASS分别签发。保留UNKNOWN/actionable=false/not_calibrated。任何阶段失败保存证据并回到最小修复，不把计划或旧收据当本次完成。

范围文件：workspace local_display_contract/read、shadow_api/chunks/client/auth；Vue消费层；TaskService/worker/action入口；local_compute/reconcile/schedule与scripts注册/CLI；相应测试/契约/当前状态。运行证据只入忽略目录，源码/去敏收据按精确路径提交。
