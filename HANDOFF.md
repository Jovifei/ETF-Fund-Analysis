# 当前工程交接

目标仍是14:30可追溯ETF/LOF研究工作台；总范围以[总路线](docs/PROJECT_MASTER_ROADMAP.md)为准。当前仅完成两批有界图表显示修复及发布文档精简，不代表S4或全项目验收完成。

## 代码与验证身份

- 仓库：`Jovifei/ETF-Fund-Analysis`；原分支：`codex/post-release-indicator-audit-20261004`。
- 本批提交前远端基线：`8c7f34209726862451b6a5379669b35cf134c593`，tree `6f604eb9fe3ef1ece3fe6cf71d1550034c10dcc6`。
- 两批实现分别统一方向显示，以及阻止原始蜡烛上的错口径研究趋势线。公式、原数值、资格、数据库及迁移未变；必要前端依赖安全更新单列验收。
- 196项前端、1762项后端/11跳过、独立138项/30投影边界、类型/构建均为已保存的源码验证。脱敏仅重核文件哈希与文档生成，不声称重新执行过这些测试。
- 新提交身份以原分支实际SHA/tree为准。精简改变文档tree；实现/测试字节仍由两份审计中的SHA-256绑定。不能把相同tree的本地基线提交当成远端父提交。

## 下一步与边界

### 浏览器认证部署契约

- 生产保持 `AUTH_ENABLED=true`，使用现有 `DATABASE_URL` 指向持久数据库；不在交接文档保存连接串或凭据。
- 生产保持 `AUTO_CREATE_SCHEMA=false`，由 Alembic 执行受审迁移；HTTPS 下保持 `AUTH_COOKIE_SECURE=true`。
- 首次安装在部署环境通过 `auth-bootstrap-admin` 建立管理员，已有部署保留数据库用户。浏览器使用数据库账号登录与安全会话 Cookie，不以旧共享 Bearer 代替成员认证。
- 具体步骤见[部署说明](docs/ALIYUN_DEPLOYMENT.md)。这些可验证的部署要求必须在文档精简时保留。

1. 从真实远端父提交非强制发布两批完整修复，检查最终tree与候选完全一致。
2. 核该SHA的ci、workspace-ci、audit-platforms，不继承旧提交成功。趋势修复的新浏览器/截图验收仍待完成。
3. 部署前核当前运行版本与可回退状态；部署、正常私有验收/R10、实体手机结果分别记录。此交接不宣称当前生产已更新。
4. S8-F0真实权限/许可、5m/15m量额单位、源时间、PIT/OOS及可行性仍为关键路径。UNKNOWN/actionable=false/not_calibrated保持，不自动激活运行时或交易。

进度JSON为唯一可编辑台账；保留S0–S9全部任务与原五维验收状态。修改后运行 `python scripts/update_project_progress.py` 及 `--check` 生成MD/HTML，不手改生成视图。

[当前状态](STATUS.md) · [当前任务](tasks/todo.md) · [方向显示审计](docs/audits/S4_U08_SR_DIRECTION_DISPLAY_20261005.md) · [趋势口径审计](docs/audits/S4_U09_TREND_PRICE_BASIS_20261005.md)

## 必要前端安全更新

发布前完整审计发现高危/严重依赖项，已在隔离副本验证Vue3.5.42、Vitest4.1.11及source-map-js1.2.2的必要闭包。新环境23文件196项前端、类型/构建通过；audit为0高危/严重/中危、余1低危。原业务与测试源码保持，后端既有1762/11结果按相同字节复用，不冒作重跑。

隔离副本的本地浏览器因socket权限在页面/断言前退出；随后精确远端CI结果见下一节。无Vitest5、强制override或门禁放宽。见[安全兼容证据](docs/audits/FRONTEND_SECURITY_COMPATIBILITY_20261006.md)。

## 原分支发布后的验证

提交 `4c74c5546f114214d88ac141462453297a9e8ca0` 的 workspace-ci `37413206428` 与 audit-platforms `37413206383` 已通过：196前端、44 smoke、5认证、18响应式、23 PostgreSQL、20 Windows。截图中的方向依据正确；图顶局部标签叠字、DPR2清晰度及不等价原始/研究价格的浏览器专项仍有验收边界。

主CI `37413206405` 为1761通过/11跳过/1失败：精简交接漏掉浏览器数据库认证部署契约，后续生产镜像步骤未运行。补回上述必要契约后，原 `test_password_auth.py` 整文件34项本地通过，无跳过；原测试保持，修复提交仍须通过新的完整CI。未部署，也不能以未变的后端源码跳过读取文档的回归测试。
