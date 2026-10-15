# 本机优先一期阻断修复与验收

Jovi已授权实际修复、测试与可回滚部署；2026-10-15补充明确：暂不使用网页GPT，由本地独立复审决策执行。基线origin/main 103522c4c8d11d20b59891d5c3d0dbc0e49cefe7；独立codex/phase1-blockers-20261015，原目录/所有数据和配置保留。不调算法/阈值、不自动交易、不伪造上游许可，不删除旧数据和失败证据。

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
2. 集中收据进GitHub；按Jovi最新授权执行本地独立交叉复审，不再以不可用网页GPT作为发布前置；不伪造网页通过。
3. 复审通过且精确CI绿后核实际生产SHA/image/schema、磁盘/RSS、当前快照/回滚资产；新一致备份、不可变镜像、最小配置overlay，保留账号/持仓/provider与LLM设置，失败回滚。
4. 本地真实执行仅使用已准入源；缺新增权限只阻断相应动作并询问。公网回执与正常私有网页消费的generation/object hash三方对账；云研究表INSERT+UPDATE与bytes两真实交易日观察，不能由scheduler=false代替。

## 完成状态

SOURCE_TESTED、WEB_REVIEW_APPROVED、DEPLOYED、NORMAL_CONSUMER_PASS、CLOUD_WRITES_RETIRED、TWO_TRADE_DAY_PASS分别签发。保留UNKNOWN/actionable=false/not_calibrated。任何阶段失败保存证据并回到最小修复，不把计划或旧收据当本次完成。

范围文件：workspace local_display_contract/read、shadow_api/chunks/client/auth；Vue消费层；TaskService/worker/action入口；local_compute/reconcile/schedule与scripts注册/CLI；相应测试/契约/当前状态。运行证据只入忽略目录，源码/去敏收据按精确路径提交。

## 2026-10-15 继续发布

- [ ] 重新核现网/main/PR48精确身份与CI；审查真实源门禁是否混淆研究展示与操作资格。
- [ ] 保留UNKNOWN，不虚填许可/单位/时点VERIFIED；以现有ProviderAdapter和真实质量门禁执行，确有新采购或权限才问Owner。
- [ ] 修复发布迁移兼容性并验证；独立复审后合main与原目录ff-only，保护现有任务/配置。
- [ ] 本机构建固定源码不可变镜像、新一致备份、核资源峰值，受控切换和回滚验收。
- [ ] 验证实际本地执行→签名上传→网站同代读取，记录真实结果及剩余两交易日门槛。

### 新发现R8：收盘任务输入语义（执行中）

1d6739a夜间真实34只抓取日线完整，quotes34只均收到但因源收盘时间超过20分钟实时窗使required partial，CLI正确退出1。现16:10slot同样受影响。先保存失败，再以明确closed-session-input-v1实现闭市材料核验：仅private、verified当日交易日、16:00后、本次完整同日15:00–16:00源时点、无其他降级或Mock才可研究计算；原realtime/partial/UNKNOWN不提升。盘中/旧日/未知日历/缺项继续阻断。最终源码重新完整测试/CI/独立复审后才合并部署。
