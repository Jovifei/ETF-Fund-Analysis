# 2026-09-12 审核整改过程

基线：33e976c85008647ca51c0dfcd458d3e66f9e55de，codex/v105-handoff-local-20260910。新分支 fix/v105-audit-blockers-20260912，不修改原接收分支、main、生产数据库或凭据。

依据：用户提供 CODE_AUDIT_BLOCKERS_20260912.md。保留其 P1-1～P1-8、P2 各项编号；代码修复、隔离测试、现场资格分别记录，不把检测阈值或 Mock 通过当成真实资格。

## A：定位当前 CI 双失败

实际读取运行34612255959的job103305387263：失败断言是test_v105_handoff.py:111的`from backend.tests.test_v103_history import instrument`导致ModuleNotFoundError: backend。不是Node弃用警告。隔离环境去掉工作目录sys.path复现失败，改用pytest测试目录中的test_v103_history导入后同一测试通过；断言及受测应用保持原样。

B：待提交数据资格、缺失mask、完整输入hash及14:30门禁。
C：待提交结算覆盖、任务状态与跨进程锁。
D：待提交Codex隔离登录、ACL、无效产物失败释放。
E：待提交前值/分组/图例/旧壳终态与固定发布清单、完整CI收据。

本文件不是生产部署或数据资格通过的声明。后续修复必须逐项补充实际验证证据，未执行项目保留明确状态。
