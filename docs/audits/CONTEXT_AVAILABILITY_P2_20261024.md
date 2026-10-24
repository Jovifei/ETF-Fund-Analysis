# 上下文 availability 类型 P2：独立修复收据

基线：Draft PR54 `b98d68390072f31591b983ed54fb1d8bf29d7c4d`；工作分支 `codex/context-availability-p2-20261024`。PR51 `bdb556f`、PR52 `109253e` 已在基线祖先内，三条原分支及根 `main` 未修改。本批只处理可选市场上下文状态字段；不改策略、Provider、账户、生产或 F 盘数据。

## 先 RED，后最小修复

真实签名 `/api/shadow/sync` 接收带非空 `items` 的自洽坏包时，旧代码返回 200 并切换批次；在磁盘上放入重算 part hash 与 manifest 身份的坏包后，Reader 会读出它，`/api/workspace/market-context` 和 `/api/workspace/indexes` 均可返回 500。RED 首轮 11 项中 8 FAIL/3 PASS；补上显式 `null`、空字符串与未知值边界后，25 项中 8 FAIL/17 PASS。所有失败均在未改生产代码的 `b98d683` 上复现。

修复仅在 `verify_bundle_integrity` 检查显式 `availability` 必须是已定义状态。字段缺省时保留旧包推导；Reader 和 HTTP API 不加宽泛异常吞噬。坏包在接收端 409 拒绝，`latest`/`previous` 与接收证明不变；已存在的坏包在读取时不可用，两个 GET 返回有原因的不可用状态，不将结果升级为可用。既有 GET 不调用 Provider/SQL 的回归仍通过。

本地未提交源码验证：新增 25 项 GREEN；六个相关后端模块 173 PASS/0 FAIL/0 SKIP。RED XML：`E:\Claude_allow\Download\ETF-chain-fix-20261023\context-p2-null-empty-red.xml`；聚焦 GREEN XML：同目录 `context-p2-focused-final-uncommitted.xml`，SHA-256 `86a77d2bee2d02424fd1549f1d4a938fb4df763bcc6de8f287e18445754d49b6`。旧 PR54 和 bdb556f 的 Windows 全量收据仅作基线，不能冒充新提交的完整验收。

## 新 SHA 全量首轮发现的独立夹具问题

`14c65a1` 的 Windows 完整 pytest 运行到 27% 出现 `test_decision_board.py::test_snapshot_marks_old_verified_quote_stale_and_keeps_anomaly_visible` 失败；单项重跑同样得到 `quote_unverified_or_degraded`，而测试期望 `quote_stale_at_snapshot_generation`。这个测试与上下文校验无代码交集。旧夹具使用当前 Mock 报价时间加 9 分钟，可能落入 11:40 午间收盘报价特例；且没有清除 Mock 自带的降级标记。仅修测试：显式设置已核时间/实时且无降级原因，把目标快照放到报价一小时后；单项重跑 PASS。原全量在 54% 经确认后仅停止本次测试子进程，退出 `-1`，没有最终 JUnit，不能称为全量失败统计或 PASS。新提交和新全量另行记录。

下一门槛：提交固定 SHA/tree、该 SHA 的 Windows 完整测试、前端/静态/安全门与精确 CI、同一“基金决策”项目普通 Chat 独立源码复审。全部通过后才按授权合 main；不部署。正常私有网页、真实收盘、手机、两交易日和数据资格仍独立待验。
