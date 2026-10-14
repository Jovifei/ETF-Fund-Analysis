# 2026-10-14 main整合与有界清理

Jovi授权整理有效功能、合入主分支、定位卡点及删除确认可重建的残留。保持Owner文件、配置、数据库、持仓、回滚资产；不部署/刷新真实行情、不reset/clean/stash、不删仍有效测试和失败证据。

当前main/origin main=e722ad5；本地/远端主候选a2adee5。已建立独立codex/main-consolidation-20261014工作树并快进接收候选，Owner根暂不换分支。

- [x] 读契约/状态/交接/lessons，fetch并核所有分支祖先和worktree脏状态。
- [ ] 把最新本地计算/展示候选纳入；独立回测d013e48按测试接收。
- [ ] 91f7447未推修复与未提交receiver-safety候选按当前v1/v2协议整合：不得删除gzip或拒绝有效v2扩展回执；保护原worktree。
- [ ] 当前规划/发布收据按有用文档合入；旧S2、已包含功能与历史审计不回带旧实现。明确记录保留原因。
- [ ] 受影响回归、完整pytest、compile/Node、Vue test/type/build、secret scan和独立最终review。
- [ ] 更新当前STATUS/HANDOFF、分支处理表/卡点，精确GitHub源码检查后快进main并切Owner根到main；若远端/Owner有新修改先重核，不强推。
- [ ] 删除root确认未tracked/可重建的.pytest_cache与列明__pycache__；保留验收截图、报告/失败收据和有效测试。路径/符号链接/注册worktree/数据保护检查必须先做。
- [ ] Hub按实际worktree上报和最终真实结果；不将源码整合/清理升格为生产/算法/手机验收。

检查失败：保持main不动、原Owner与未提交候选不动，在隔离树最小修复并重跑相关检查。不确定来源/用途的残留不删除。

主要触及：backend/app/workspace接收/合同/投影、backend/tests对应回归，独立backtest/crosscheck修复，docs/contracts/当前状态交接、tasks记录。注册任务/生产数据库/许可/PIT/OOS/自动交易不在本轮变更范围。运行时版本/资格保持已有显式门禁；回测公式版本按d013已升级版本核对，不自行改阈值。
