# 当前生产身份只读核验 — 2026-10-02

用途：修正总路线图的过期部署事实；不替代完整发布、功能或数据资格验收。只读取容器/镜像所选标签和数据库元数据，未读取凭据、账户或持仓，未写生产数据库。

| 项目 | 当前观察 |
| --- | --- |
| GitHub main / 本地主线 | 63c426aa9954d950d397c56ad0ece6273da6f19d |
| 该提交Git tree | 30906b8b325a68c456d222abc7f48c3c354c793f |
| API/worker/scheduler镜像revision标签 | 三者均63c426aa9954d950d397c56ad0ece6273da6f19d |
| 三服务配置digest / Docker image ID | sha256:b07f9ca23150db6567170d3a041afb0abf65d571fbd45ce44266585ee62366b5 |
| API创建时间 | 2026-10-02T04:58:51.111871873Z（上海12:58:51） |
| Worker/scheduler创建时间 | 2026-10-02T04:58:52Z附近 |
| 服务状态 | API/worker healthy；scheduler running；三者restarts0 |
| 数据库Alembic | f0e1d2c3b4a5 |
| 最新决策板generated_at | 2026-10-02 13:29:31.364035+08:00 |
| 最新决策板read_model_version | decision-read-v109-flow-share |
| Chan运行配置 | enabled=false，qualification_status=BLOCKED，selection_status=SELECTED_DISABLED |

镜像源码标签与GitHub提交一致，但本轮未重算镜像文件来源/构建树一致性，也未独立审查新功能；健康和最新快照版本不能证明合同兼容、量额资格、统计效力或功能完整验收。

3a13575/h9是本聊天此前发布的历史基线。iteration71的9/13清单仅保留为该旧基线记录，不能套用到63c426a/f0。旧h9上的IMAGE_ONLY回滚演练不能直接证明f0新迁移回滚兼容。

当前接收需要查明63c426a发布的授权/完整收据、测试、备份恢复迁移回滚证据、图层语义和正常用户私有读取行为。已上线功能状态应写“DEPLOYED_PENDING_INDEPENDENT_ACCEPTANCE”，避免继续写“候选未部署”。
