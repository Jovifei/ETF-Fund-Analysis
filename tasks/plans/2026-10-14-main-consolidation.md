# 2026-10-14 main整合与有界清理

Jovi授权整理有效功能、合入主分支、定位卡点及删除确认可重建的残留。保持Owner文件、配置、数据库、持仓、回滚资产；不部署/刷新真实行情、不reset/clean/stash、不删仍有效测试和失败证据。

启动基线main/origin main=e722ad5、主候选a2adee5；完成时PR46已合并，Owner根已快进到main，工作树干净。实际源码、测试及后继文档身份见整合收据。

- [x] 读契约/状态/交接/lessons，fetch并核所有分支祖先和worktree脏状态。
- [x] 把最新本地计算/展示候选纳入；独立回测d013e48按测试接收。
- [x] 91f7447未推修复与未提交receiver-safety候选按当前v1/v2协议整合；保护原worktree。
- [x] 当前规划/发布收据合入；旧S2和历史分支的保留原因已记录。
- [x] 受影响回归、完整pytest、compile/Node、Vue test/type/build、隔离源码secret scan和独立本地review；精确源码CI通过。
- [x] 更新STATUS/HANDOFF和卡点；PR46合main，Owner根快进对齐，未强推。
- [x] 原目录缓存整理：递归删除被自动审批拒绝，改可回滚归档19目录；有效测试和证据保留。
- [ ] Hub连接拒绝，最终摘要本地暂存；恢复后读取实际revision再生成事件。网页端连接复审尚未通过。

结果：[MAIN_CONSOLIDATION_20261014.md](../../docs/audits/MAIN_CONSOLIDATION_20261014.md)。

检查失败：保持main不动、原Owner与未提交候选不动，在隔离树最小修复并重跑相关检查。不确定来源/用途的残留不删除。

主要触及：backend/app/workspace接收/合同/投影、backend/tests对应回归，独立backtest/crosscheck修复，docs/contracts/当前状态交接、tasks记录。注册任务/生产数据库/许可/PIT/OOS/自动交易不在本轮变更范围。运行时版本/资格保持已有显式门禁；回测公式版本按d013已升级版本核对，不自行改阈值。
