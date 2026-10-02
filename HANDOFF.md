# 新工程接手入口

从main继续，先读[状态](STATUS.md)、[总路线](docs/PROJECT_MASTER_ROADMAP.md)、[进度](docs/PROJECT_PROGRESS.md)。当前优先S8-F0数据可行性，与63c426a上线功能的独立接收并行。

## 当前边界与下一动作

- 当前观察63c426a/f0/v109；持久化Chan与简化回退语义、量额/时间、新迁移回滚和收据仍待审查。
- 正常用户私有验收登录问题已提出，勿重复索取密码/Token/Cookie，不绕过鉴权或创建生产测试用户。
- 真实数据UNKNOWN、actionable=false、Chan未激活；本轮主线收尾不部署生产。
- 远端把关方向与关键合同；低风险按已有授权本地推进、阶段批次回传，连接不可用不冻结全部工作。

按[S8-F0计划](docs/planning/S8_F0_DATA_FEASIBILITY_SPIKE.md)核5m/15m量额/时间/PIT/许可成本，调查未执行；付费/许可升级给Jovi具体选择。同步接收已上线图层/份额，避免重复实现。

每次实质变化更新进度JSON并运行python scripts/update_project_progress.py及--check。[维护契约](docs/PROJECT_PROGRESS_MAINTENANCE.md)定义证据和风险分级。新工程使用项目内隔离分支。

## 正常账户与部署

生产数据库认证：AUTH_ENABLED=true、AUTO_CREATE_SCHEMA=false、AUTH_COOKIE_SECURE=true；DATABASE_URL由受保护环境传入，禁止读取或回显值。正常初始化运维入口fund-decision auth-bootstrap-admin由有权限人员在确需时使用；已有账户通过浏览器正常登录，本轮不执行初始化。见[部署清单](CODEX_DEPLOYMENT_TASKS.md)。

[旧交接长账本](docs/archive/project-simplification-20261002/HANDOFF.md)已归档。数据库、备份、证据、NOTICE及含未提交资料的工作区保留。
