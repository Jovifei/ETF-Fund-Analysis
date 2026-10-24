# 部署检查清单

本批修复与文档整理不自动部署。最新身份和阻塞见[STATUS](STATUS.md)，完整操作见[阿里云手册](docs/ALIYUN_DEPLOYMENT.md)。

1. 核精确源码/镜像、权限、测试和复审，不从版本标签或上传包推断已部署身份。
2. 新一致备份校验且回滚可执行后，按获准范围部署；需要迁移时走受审Alembic，不能直接写生产表。
3. API/worker/scheduler、鉴权、Provider audit、同代页面及资源分别核验，失败受控回滚。
4. 保留失败收据、数据和用户修改；不清理另一AI的服务器备份或服务。

生产AUTH_ENABLED=true、持久DATABASE_URL、AUTO_CREATE_SCHEMA=false、AUTH_COOKIE_SECURE=true。首次管理员由auth-bootstrap-admin初始化；已有用户/持仓保持，浏览器正常登录，不读取或回显凭据。

文档/样式验证不冒充真实运行。正常登录消费、自然两交易日、手机与PIT/OOS资格单列；health200/accepted/CI不能互相代替。历史镜像/收据按其固定日期理解。
