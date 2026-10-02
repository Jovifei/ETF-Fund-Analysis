# 当前部署检查清单

按已有授权及[总路线风险分级](docs/PROJECT_MASTER_ROADMAP.md)执行，版本以SHA与镜像证据为准。

1. 核源码、测试、当前线上版本、范围与阶段审查。
2. 生产先备份并验证完整性，保留可执行回滚。schema变化/兼容性不确定时演练恢复迁移回滚；文档/样式不重复全套。
3. 使用精确审核镜像和受审计Alembic迁移，不直接改生产业务表。源码同步git pull --ff-only。
4. 查API/worker/scheduler、鉴权、Provider审计和受影响功能；需刷新衍生快照时用现有审计任务，核对最终版本。
5. 失败按验证的方案回滚；记录源码/镜像/schema/功能证据，更新状态和进度，批次回传。

## 数据库浏览器认证

AUTH_ENABLED=true、AUTO_CREATE_SCHEMA=false、AUTH_COOKIE_SECURE=true；DATABASE_URL受保护配置，禁止读取/回显/提交真实值。正常初始化入口fund-decision auth-bootstrap-admin，仅有权限人员在确需时使用；已有账户通过浏览器正常登录。不得读密码、Cookie或Token、绕过鉴权或用生产测试账户替代验收。

当前观察63c426a/f0/v109，完整独立接收待核对，真实数据UNKNOWN、actionable=false，无自动交易。见[身份](docs/audits/CURRENT_PRODUCTION_IDENTITY_20261002.md)、[阿里云说明](docs/ALIYUN_DEPLOYMENT.md)。[旧清单](docs/archive/project-simplification-20261002/CODEX_DEPLOYMENT_TASKS.md)归档，不是当前操作授权。
