# 当前工程交接

当前任务是Jovi授权的main整合与有界清理；生产、数据、算法资格与源码合并分别验收。详细整合收据：docs/audits/MAIN_CONSOLIDATION_20261014.md；完整本机到网站路线：tasks/plans/2026-10-11-local-live-to-website.md。

## 接收与保护

1. fetch后核main/HEAD/工作树和整合收据的真实SHA/tree，不用旧分支标题判断最新版。保护Owner未提交/忽略文件、配置、DB、账号/持仓、任务与回滚资产；不reset/clean/stash。
2. 按Python3.12、Node>=22.18和实际lockfile验证；同一lockfile不保证node_modules实际版本一致。回归/static/frontend/CI结果按精确源码绑定，不继承为生产或手机通过。
3. 接收安全v1.1/v2.1保留wire合同、gzip与不同回执；历史STALE读取不自动授权过期包激活，当前版本绑定与前端跨请求pin仍是卡点。
4. 独立回测d013e48升级backtest_version至0.5.8-observed-mark-ledger，会改变strategy config_hash；生产重新验收前不沿用旧包/回执。

## 下一顺序

先确认main整合测试/CI与本地分支已对齐；随后完成过期/code-config/generation/端点语义、cloud所有写入口退休和有界真实运行验收。不要重复已合的旧实现，不删除有效测试或失败收据。真实源许可/PIT/OOS、未校准预测、正常私有访问/零副作用、实体手机与图表专项保持独立门槛。源码整合不表示本轮生产发布。

## 浏览器认证部署契约（必须保留）

- 生产保持AUTH_ENABLED=true；现有DATABASE_URL指向持久数据库，保留用户与持仓，不把本机展示库替换成账户DB。
- AUTO_CREATE_SCHEMA=false；由Alembic执行受审迁移，HTTPS保持AUTH_COOKIE_SECURE=true。
- 首次安装通过auth-bootstrap-admin创建管理员；已有部署保留原数据库用户。浏览器使用数据库账号与安全会话Cookie。
- 部署前新备份、不可变镜像与可回滚配置；通过精确CI后才能按授权发布，失败受控回退。详见docs/ALIYUN_DEPLOYMENT.md。

进度JSON仍是全部S0–S9任务台账，生成MD/HTML不手改；本文件只记录当前交接，不改最终目标、阈值或资格。UNKNOWN/actionable=false/not_calibrated和无自动交易保持。