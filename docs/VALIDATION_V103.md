# v1.0.3 验证与证据边界

最终结果以固定交付提交关联的Actions及交付收据为准，不能拿祖先提交全绿替代新提交验收。

## 过程记录

- Stage1：历史隔离与v1.0.1数据专题34项通过。
- 本机前端：8个Vitest文件24项、typecheck、build通过；容器Node22.16低于推荐patch，正式CI使用满足engines的Node22.23.2。
- 全量回归先发现原盘中研究状态被历史回退误清，已修复；版本测试由旧1.0.1断言改为核对pyproject/Settings/前端package与lock同时为1.0.3。
- 新增离线任务与首次指数注册表2项通过。缓存重算不因缺Token实例化上游SDK。
- 本机Chromium在URL导航时被策略拒绝ERR_BLOCKED_BY_ADMINISTRATOR，没有绕过策略或删测试，转云端真实HTTP Playwright。

## b0e5f82b 云端验收

固定提交：b0e5f82bd8f4716e69836108ce45940305779ff3。
workspace-ci https://github.com/Jovifei/ETF-Fund-Analysis/actions/runs/34300195856 成功：专题、audit、类型、24项Vitest、build、普通浏览器11项和认证1项全部通过。报告stats无跳过、无flaky；截图包括真实原模板内收藏、指数蜡烛图、AI连接指引。

原完整ci https://github.com/Jovifei/ETF-Fund-Analysis/actions/runs/34300195829 失败：843项中841通过/1跳过/1失败。唯一失败是根HANDOFF重整后遗漏了显式认证部署键，不是业务用例失败。已恢复AUTH_ENABLED、DATABASE_URL、AUTO_CREATE_SCHEMA、Secure Cookie和仅空库bootstrap说明；保留原测试并再次运行全套CI。该旧失败记录不能写成全绿。

工作站证据artifact 10084683589 SHA256=764cec792005f90cecaba41f3392b9f5a5fa595a799a194622318a25e3193488。原artifact为PR测试合并树a3df3620，head对应b0e5f82b；三处关键应用文件哈希与已审查source一致，一次性传输材料与apply工作流已清除。

## 最终CI门禁

ci：pytest全量、compileall、旧JS、secret scan、干净SQLite迁移、ShellCheck、Compose、生产镜像构建、隔离PostgreSQL容器smoke。
workspace-ci：原工作站和v101/v102/v103专题、npm audit high门禁、类型、Vitest、build、真实Chromium普通与认证旅程、截图与trace。

单元和浏览器的Mock资产显式actionable=false。PostgreSQL条件单测没有TEST_POSTGRES_URL时允许条件跳过，不能称为已跑；镜像中的PG迁移smoke是另一项证据。

## 本地待执行

见[LOCAL_ACCEPTANCE_V103.md](LOCAL_ACCEPTANCE_V103.md)的L1–L5：真实ETF和三指数数据、原持久库联调、断网/重启缓存、OCR实际模型、本人Codex/Vibe登录与有预算的单次报告。无凭据不访问用户账户，不能假造真实验收。
