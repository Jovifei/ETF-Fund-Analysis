# 当前状态 — 2026-10-02

个人ETF/LOF研究工作台，无自动交易。main已收拢R4C持久化读模型、图表研究层、流量/份额研究字段和总路线/进度文档。

## 当前部署与资格

- 观察应用源码：63c426aa9954d950d397c56ad0ece6273da6f19d；三服务镜像配置digest b07f9ca23150db6567170d3a041afb0abf65d571fbd45ce44266585ee62366b5。
- Alembic f0e1d2c3b4a5；决策板2026-10-02 13:29按decision-read-v109-flow-share生成。
- 图层/份额相关实现已部署；完整发布收据、合同兼容与私有功能独立接收待核对。
- Chan运行关闭；真实数据UNKNOWN、actionable=false、预测not_calibrated。
- 本轮主线整合与清理不改变生产应用源码或数据库。

## 下一阶段

优先[S8-F0数据可行性](docs/planning/S8_F0_DATA_FEASIBILITY_SPIKE.md)，与当前S3/S4接收和发布硬化并行；调查尚未执行。方向决定前暂缓S5–S7扩张。取得数据不等于统计有效，后续需最小基准、PIT/OOS和资格证据。

## 权威入口

[总路线](docs/PROJECT_MASTER_ROADMAP.md) · [进度](docs/PROJECT_PROGRESS.md) · [图形板](docs/PROJECT_PROGRESS.html) · [当前身份](docs/audits/CURRENT_PRODUCTION_IDENTITY_20261002.md) · [本轮收尾](docs/audits/MAIN_CONSOLIDATION_CLEANUP_20261002.md) · [交接](HANDOFF.md)。

Git文档提交不等于生产已更新。文档提交用git log -1查询，生产源码单列。旧3a/h9的iteration71 9/13和回滚证据仅历史。[旧状态长账本](docs/archive/project-simplification-20261002/STATUS.md)已归档。
