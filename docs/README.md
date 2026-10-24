# 文档地图

常用入口只保留一条主线：

| 目的 | 入口 |
| --- | --- |
| 产品与数据位置 | [README](../README.md) |
| 当前事实与验收 | [STATUS](../STATUS.md) |
| 启动/正常访问 | [QUICKSTART](../QUICKSTART.md) |
| 工程接手 | [HANDOFF](../HANDOFF.md) |
| 数据流与边界 | [ARCHITECTURE](ARCHITECTURE.md) |
| 产品下一步 | [路线](PROJECT_MASTER_ROADMAP.md) |
| 阶段证据计数 | [JSON台账](PROJECT_PROGRESS.json) · [生成视图](PROJECT_PROGRESS.md) · [维护规则](PROJECT_PROGRESS_MAINTENANCE.md) |

## 专业参考保留

- [AGENTS](../AGENTS.md)、[部署](ALIYUN_DEPLOYMENT.md)、[AI连接安全](AI_CONNECTION_SECURITY_V104.md)。
- [支撑压力语义](SUPPORT_RESISTANCE_SEMANTICS.md)、[盘中刷新](INTRADAY_REFRESH_CADENCE.md)、[14:30工作台](ETF_1430_DECISION_WORKBENCH.md)。
- [调度/恢复](contracts/LOCAL_CADENCE_V1.md)、[报价路由](contracts/QUOTE_ROUTE_DEFERRAL_V2.md)及contracts目录的其他接口合同。
- [本轮链路验收](audits/LOCAL_FIRST_CHAIN_20261023.md)及audits目录的原始发布/失败/回滚证据，按日期和固定源码理解。
- LICENSE、[第三方NOTICE](../THIRD_PARTY_LICENSES/NOTICE.md)、frontend/NOTICE和开源登记保留。

## 历史与兼容

旧方案精华已归纳到当前架构和路线；[HISTORY](HISTORY.md)提供Git恢复方式。仍被程序、测试、生成器或保留收据引用的旧路径保留，是兼容/证据入口，不是今天的新操作说明。

不删除业务代码、有效测试、私有配置、数据库、备份、回滚资产或另一AI处理的服务器资料。
