# v1.0.3 验证与证据边界

此文是交付前的测试记录，最终CI结果以固定应用提交关联的Actions及交付收据为准；不把历史绿色构建当成新提交全绿。

## 已执行

- Stage1：历史隔离与v1.0.1数据专题34项通过。
- 前端：8个Vitest文件24项通过、typecheck、生产构建通过（本容器Node22.16，低于推荐patch；正式CI使用满足engines的Node22）。
- 全量回归曾发现原盘中研究状态被历史回退误清，已修复；重跑后仅剩旧版本断言失败，839通过/1跳过/1失败。版本测试已改为同时核对pyproject、Settings、前端package与lock为1.0.3，单独回归通过。
- 新增离线任务与首次指数注册表2项回归通过；避免没有Token时连已存历史都不能重算。
- 本容器Chromium在导航时被策略拒绝ERR_BLOCKED_BY_ADMINISTRATOR，不能把本机E2E标通过；同一真实HTTP Playwright套件提交workspace-ci执行，不删除或跳过断言。

## 最终CI门禁

ci：pytest全量、compileall、旧JS、secret scan、干净SQLite迁移、ShellCheck、Compose、生产镜像构建、隔离PostgreSQL容器smoke。
workspace-ci：原工作站和v101/v102/v103专题、npm audit high门禁、类型、Vitest、build、真实Chromium普通与认证旅程、截图与trace。

单元和浏览器的Mock资产显式actionable=false。PostgreSQL条件单测没有TEST_POSTGRES_URL时允许条件跳过，不能称为已跑；镜像中的PG迁移smoke是另一项证据。

## 本地待执行

见[LOCAL_ACCEPTANCE_V103.md](LOCAL_ACCEPTANCE_V103.md)的L1–L5：真实ETF和三指数数据、原持久库联调、断网/重启缓存、OCR实际模型、本人Codex/Vibe登录与有预算的单次报告。无凭据不访问用户账户，不能假造真实验收。
