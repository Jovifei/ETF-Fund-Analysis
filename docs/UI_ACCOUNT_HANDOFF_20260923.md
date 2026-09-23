# 登录、个人中心与 K 线指标管理交接（A-U1–A-U3）

日期：2026-09-23。此文是已实现代码的分阶段接收合同，不是完整联系方式绑定、永久删除或生产上线收据。

## 1. 固定身份

| 用途 | SHA |
| --- | --- |
| 基线 main | `56a5378fce884c82462df90e3eea88add230f1a0` |
| A-U1 后端账号自助 | `8ad47f57d8da1bf2ef3ee6756980a252c6c6ec50` |
| A-U2 登录、个人中心、指标管理 | `f1317c8a2976d9977d59324640ea849b667ec611` |
| A-U3 短屏弹层和 Esc 修复，固定应用 | `65d5a2c4fc228cc37e4ade3d6f81085edee64107` |
| 固定应用 Tree | `aca5774c901342a835867a05b837cc91bddce448` |

仓库为 `Jovifei/ETF-Fund-Analysis`，接收分支为 `codex/v106-scheduler-oom-fix`。相对基线 ahead3/behind0，共19个应用和测试文件变化。应用/前端版本仍1.0.5，Alembic仍为e609200001，本批未新增迁移。文档后续提交与固定运行代码分开。

候选分支完整通过ci、workspace-ci、audit-platforms后，才以force=false快进接收分支；没有修改main、删除历史分支、移动标签或部署生产。下载同SHA的source.tar重建Git索引，完整Tree与上述值一致；上传Git树也与本地暂存树一致。

## 2. 已实现与未实现

用户截图只作布局参考。保留本项目ETF Research品牌、原工作站与数据合同，不复制参考站Logo、地图、原截图电话或个人资料。预览来自隔离虚构账户和Mock行情。

### 已实现

- 登录/邀请注册卡片、深浅主题、密码显隐、真实会话加载状态及工作站切换；不虚构接入全球市场，不增加固定动画等待。
- 个人资料、安全、偏好、我的AI分区；当前身份、日期、权限/权益、登记邮箱遮罩；昵称保存不改变登录名、角色或其他账户。
- 新账号自助路由：`GET /api/workspace/account`、`PATCH /profile`、`PUT /password`、`POST /closure`。强制数据库会话和CSRF，敏感操作重新核对当前密码，持久化尝试限制，验证错误不回显密码，响应no-store。
- 修改密码后撤销全部浏览器会话。关闭访问需要当前密码、明确确认语和数据保留勾选；撤销设备/研究任务，保护最后管理员。
- MA/BOLL主图与MACD/KDJ/RSI副图的选择、移除、恢复默认；有观测值的成交量可显隐。图层切换保留原蜡烛实例，服务端公式和参数不变，缺值不补零。
- 指标菜单按可视窗口和缩放/偏移选择上下位置，滚动/resize时更新；短屏底部按钮可达。Esc先关闭指标弹层，再退出应用fallback全屏，原生浏览器保留键不作跨平台保证。

### 明确未实现

邮箱验证码、短信发送与验证、绑定/更换邮箱或手机号、微信OAuth扫码绑定/解绑、忘记密码找回、永久数据擦除。现有按钮明确不可用，登记邮箱不等于所有权验证。这些尚需后端流程和真实渠道，不能说“只缺一个Key”。

当前注销仅禁用登录访问，持仓、自选、报告、研究记录和备份仍保留，不可命名为永久删除成功。

EMA/SAR/BBI等新增算法、任意指标参数编辑、所有分钟周期、完整画线工具、完整缠论结构、本地Codex本人接通，以及R2–R6更新/数据资格路线，没有因本次页面优化而完成。原始价格、策略和actionable没有改变。

## 3. 修复与测试证据

A-U3先在f131组件上复现2个失败：短屏菜单截断；Esc同时关闭菜单和fallback全屏。之后新增仅处理几何的popupLayout与回归。首次TypeScript错误来自测试fixture漏amount，补为amount:null后通过，没有关闭类型检查或降低业务断言。

固定应用的五类原生CI证据：

| 工作流 | Run ID | 结果与位置 |
| --- | --- | --- |
| ci | 35808575425 | completed/success，隔离候选 |
| workspace-ci | 35808575427 | completed/success，隔离候选 |
| audit-platforms | 35808575452 | completed/success，隔离候选 |
| postdeploy-ci | 35809368430 | completed/success，同SHA接收分支 |
| acceptance-tooling | 35809368429 | completed/success，同SHA接收分支 |

以上均绑定65d5a2c，不跨SHA拼接。快进触发的重复ci/workspace/audit运行不是本次必须等待的额外版本，未结束的重复运行不冒充PASS。后续纯文档提交不改变应用测试对象。

实际解析JUnit和浏览器报告：后端全量1221项，1218通过、3条件跳过、0失败/错误；工作站后端267项，266通过、1条件跳过；普通浏览器18/18、认证5/5、响应式18/18，retries=0，0失败/0跳过/0flaky；Windows专项20/20，专用PostgreSQL23/23，Windows归档19/19。各专项与全量重叠，不能相加为唯一用例数。

全量3个skip是Windows NTFS、专用PostgreSQL、可选DuckDB，分别由同SHA独立任务覆盖。Vue48/48、A-U3聚焦8/8、账号后端18/18、旧JS全部39/39（CI三文件子集27/27）、typecheck、额外E2E类型检查、构建、compileall、密钥扫描、diff检查、临时SQLite upgrade/check/current均有实际证据。

镜像build/smoke和runtime inventory已完成，但registry digest未发布，release_inventory_complete=false，production_deployed=false，data_qualification=not_asserted。

### 本机环境限制必须保留

本次审查环境Python3.13.5、Node22.23.2；CI使用Python3.12等独立平台。首次本机完整1221项是1216通过、3失败、2条件跳过：两个子进程缺app路径，经显式PYTHONPATH=backend后原用例2/2通过；另一个可选AKShare缺包未在此环境解决。未删除/弱化该测试，不能将本机全量记PASS；完整market-enabled原生CI已运行该路径。

本机Chromium在HTTP导航被托管策略ERR_BLOCKED_BY_ADMINISTRATOR拒绝，业务断言未执行。保留日志，未调整或绕过策略；真实浏览器验收来自项目原生Actions runner。

依赖审计仍为1 low、2 moderate、0 high/critical（esbuild、vitest、@vitest/mocker，开发/测试树），保留风险；未执行未经批准的major强制升级，不宣称零漏洞。

## 4. 本地 Codex 接收步骤

1. 阅读AGENTS.md、本文件和相关测试。在全新独立目录接收固定应用65d5a2c；核对HEAD、HEAD^{tree}及基线祖先。保护E:\project\ETF-Fund-Analysis和所有旧目录，不reset/clean/stash/覆盖，不读取或回显.env、Cookie、Token或密码。
2. 创建Python3.12 venv，按pyproject安装dev/market/archive所需依赖，Node22满足>=22.18，npm ci按锁安装。只使用临时数据库；APP_ENV=test、MARKET_PROVIDER=mock、ALLOW_MOCK_FALLBACK=false、LLM_ENABLED=false、ANALYSIS_ENABLED=false；显式PYTHONPATH指向backend，不能继承生产DATABASE_URL。
3. 先跑`python -m pytest backend/tests/test_account_self_service.py -q`，再跑完整`python -m pytest -q --junitxml=<evidence>/full.xml`。保存初次失败、修复原因与完整重跑；缺环境只能SKIPPED_ENV。
4. 执行compileall、密钥扫描、旧JS全部测试、npm test/typecheck/build、npm audit --audit-level=high和git diff --check。不要npm audit fix --force。
5. 独立SQLite upgrade/check/current应到唯一head e609200001。按现有CI命令验证专用PostgreSQL16和Windows条件；不能拿生产库代替测试库。
6. 在frontend目录依次执行`npx playwright test --config playwright.config.ts`、`playwright.auth.config.ts`、`playwright.responsive.config.ts`。PATH中的Python须为本次venv，使用虚构账户/Mock行情，retries=0。预期范围18/5/18，具体以实际同SHA报告为准。
7. 人工复核：登录主题/注册切换、真实会话过渡；手机/桌面个人中心、昵称持久化；错误密码不修改/锁定限制/改密旧会话失效；普通虚构用户关闭访问但记录保留，最后管理员保护；未实现验证渠道禁用。
8. 图表复核：主副图增删不替换蜡烛、不调用模型或数据写入；320至4K、390x600短屏、缩放、触摸/DPR2、方向与全屏；菜单最后按钮可达，Esc和焦点正确。实际Safari/软键盘/原生保留键没验证就写UNKNOWN。
9. 测试服务默认由Playwright退出，不能把端口当作持久预览。需要持久预览时另行记录实际绑定127.0.0.1的进程、隔离库及启动/停止方式。
10. 输出RECEIPT_UI_ACCOUNT_20260923.md和DECISION.md，分别判断代码接收、外部验证渠道、真实数据资格和生产部署。此次不自动合并main、部署、发送验证码、本人模型登录或付费调用。

## 5. 后续渠道实现，不是本批完成项

A-U4先实现版本化ContactIdentity、VerificationChallenge和审计实体：挑战绑定用户/用途/目标/到期/尝试次数/一次性消费；邮件短信服务端适配器；真实投递、限流和费用边界；重新认证后验证新联系方式，事务唯一性/原子切换、通知原方式；重复/过期/跨用户/并发/投递失败拒绝用例。

微信使用官方授权回调身份，state绑定会话与用途，校验回调、code一次性和身份冲突；手填微信号不授予绑定。外部应用和凭据在用户受控环境配置，不进仓库。忘记密码、解绑及丢失旧联系方式恢复单独设计。

A-U5另定义永久删除范围：个人记录、设备、文件、报告与备份的处理和保留证据；实现删除任务、确认与完成收据。不把当前禁用访问改个标签冒充永久擦除。

参考：OWASP Authentication Cheat Sheet（敏感操作再认证和会话管理）、MDN VisualViewport（可视范围与resize/scroll），无新增第三方运行依赖。本批源码与依赖锁不含第三方站点的私有资产或原截图身份数据。
