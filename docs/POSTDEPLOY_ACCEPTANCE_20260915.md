# v106 后续修复：固定提交验收收据（2026-09-15）

## 固定身份

- 仓库：Jovifei/ETF-Fund-Analysis。
- 现有分支：fix/v106-postdeploy-20260914；PR #34 保持既有目标分支，不合并 main。
- 接续基线：e44e9deb085579f2fe69c3461fda53d0f4ffbe93。
- 固定应用与测试提交：**c219185e608dc95e4d3e82e8142c08a9590eca94**。
- 固定源码树：**c5d13ef4f92d850e58840e66f7447f3d4247ec0c**。
- 应用/前端版本 1.0.5；Alembic head d40609090002。v106 是分支批次名，不是发布标签。

本轮修改代码并分步推送现有分支；没有部署生产、修改 main/标签、访问真实持仓库、本人登录或调用付费模型。之前已由其他阶段完成的收盘恢复、决策板日期/计数/空情景、S/R 与 ShellCheck 修复沿基线保留，不宣称本轮重新实现。

## 七个分步提交

| 提交 | 内容 |
|---|---|
| 9a08996d0b180650ae3cf9b4200bf27a7bac56d1 | 月度价格研究的连续性/价格基准、NaN 输入及缓存失效 |
| c0ed83fa4a2e94cbf1cd99817d8a84406afc2a54 | iframe 保留缓存同时显示请求错误；新增只读专项 CI |
| d0f61cbfb5f447a9d1255150f565b2d85852eb45 | 私有离线归档协议、签名校验、Parquet/ZSTD 和 CLI |
| 2269fb5d81e93c837aae5ad589be44e9c16092a5 | 下破误判、缺失 KDJ/RSI/预测输入数值转换与回归 |
| 54851e17897f8d16062dfb07113204e884285d1a | 详情快照合同、相关性断点、目标日覆盖和健康页摘要 |
| 65e49867a65a45e2fb3674457c568e0e6b0fa8ab | 全历史流式 hash、分标的资格检查、释放重复帧及 hash 复用 |
| c219185e608dc95e4d3e82e8142c08a9590eca94 | 原生 Windows NTFS 隐私拒绝与实际 Parquet 归档测试 |

GitHub compare 核对：相对 e44e9de ahead 7、behind 0，23 个文件变化。后续仅文档提交单独记账，不改变固定应用 SHA。

## 最终固定提交的四套 CI

以下状态均通过 GitHub API 最后核对为 completed/success；JUnit 与 Playwright 内嵌报告已下载读取，不只看绿色徽标。

| 流水线 | Run | 实际证据 |
|---|---|---|
| ci #657 | 34920325120 | 全量 1061：1058 通过、3 条件跳过、0 失败/错误。编译、旧 JS、密钥扫描、Alembic、ShellCheck、Compose、生产镜像构建、smoke、inventory 成功。 |
| workspace-ci #180 | 34920325126 | 后端专项 258：257 通过、1 Windows 条件跳过；前端 test/typecheck/build/audit 成功；普通 HTTP Playwright 18/18、认证 2/2，0 flaky、0 skipped。 |
| audit-platforms #47 | 34920325125 | 实际 Windows Bridge/NTFS 17/17；专用 PostgreSQL 16 测试 23/23。 |
| postdeploy-ci #12 | 34920325127 | Python 3.13 后续专项 81/81；新增嵌入表 JS 回归成功；原生 Windows Python 3.12 归档/ACL/Parquet 19/19，均无跳过。 |

全量中的三个跳过分别为实际 Windows NTFS、显式 TEST_POSTGRES_URL、未安装可选 DuckDB。它们分别由独立 Windows、PostgreSQL 和安装 DuckDB 1.4.5 的归档任务执行覆盖。不能把各专项重复用例相加当成唯一用例总数；CI Windows 也不等于用户 E 盘现场资格。

## 源码与本地复核

workspace 产物 source.tar 的 Git PAX comment 为 PR 合并验证对象 630627dfe24dc990b91d70e7cfbf0f6eb2748dd9。解包重建完整 Git tree 后，树与固定分支提交 c219185 完全相同，为 c5d13ef4f92d850e58840e66f7447f3d4247ec0c。原有 .gitignore 忽略但 Git 跟踪的 deployment_reports 需包含在完整树核对中；最初未包含时的不匹配已查明，不靠修改应用文件对齐。

在这份实际远端源码上，本地 Python 3.13 + 实际 pwdlib 0.3.1 / DuckDB 1.4.5 再验：后续专项 81/81、旧表/嵌入/路由/刷新 JS 合计 28/28，compileall、JS 语法与 diff check 通过。

早期本地候选曾跑过全量 1059 项（0 失败、3 条件跳过），但该树含两个最终未提交接线，不能替代本收据中最终远端 1061 项结果。失败反例、中间修复与环境条件单独保留，不改写成一次就全部通过。

## 产物定位和 SHA-256

| 产物 ID | 内容 | 下载 ZIP SHA-256 |
|---|---|---|
| 10377703836 | 全量 JUnit / release-inventory | 4eb3e77af98820b59bc0717fb55870af2014d2bf8ddbb0d4aec0d5c113a7da7c |
| 10378111617 | 固定源码 tar / 后端专项 / 两套浏览器报告 | 5ca0ca75fb7cc4ce3c89bfd0a644ce0e66c1886072b2d425da49300a13873547 |
| 10378250137 | PostgreSQL JUnit | 03371a3d2d3fe938167c009d2ef4dc9e2b5b1e7bbed04559aa30c1ace593fd1c |
| 10377314661 | Windows Bridge JUnit | d07fd0c52e6707154e5b2208081c9f6c69a18c822dba753de389106f10a0184c |
| 10378325394 | 后续专项 / 依赖 inventory | 115d8d7b6b99603e546a55ee583e4ecc601937a437a1c419b07ea5050b00cda0 |
| 10377613416 | Windows 归档 JUnit | 425b573dea4b807e9190fe38682fb4cdce6e068a785a4f31f90698d9eb892a8c |

GitHub 产物有保留期限。本地交接包只保存必要 JUnit、报告统计和 inventory，不含第三方轮子、字体、真实数据库或凭据。不得保存临时签名下载 URL。

## 发布 inventory 的边界

CI 镜像 ID：sha256:f9286123f8a0de1e27f65bd26f7ec04cdf7bcc1c1809b4d93bc5f5586c704704。
前端构建树 hash：b5626f2a1d175fde10d52f0cdc507724b85c9ff871e7cc3f36591d74f4f156a0。
运行时包 inventory hash：586b411ff4c2151b9bf6cfa9dfb452112d55eaa0020b0112af4372dcbfd27f82。

已产生 CI 实际运行时包 inventory；仍未发布 registry digest，missing=[published_image_digest_missing]，release_inventory_complete=false。image ID 不冒充 registry digest；production_deployed=false、data_qualification=not_asserted。生产应对实际采用的镜像、源码挂载和依赖另行生成收据。

## 两处未提交和真实剩余项

worker.py 的安全摘要委托与 workspace/api.py 的显式 settings 传递在整文件 GitHub 写入时被平台安全检查拦截，未绕过，未进入固定远端提交。新 task_summary 已用于 data-health，但工作站 worker 的 ETF 明细省略问题尚未完整关闭；research-outlook read 的默认 get_settings 仍工作，依赖注入配置一致性待审。交接包不含自动应用被拦截代码的脚本。

未实现：在线归档请求 owner/队列、主动 HTTPS agent、消费/防重放账本、TTL 缓存与自动云地回取；完整公司行动/总收益调整器。未现场认证：scheduler 真正终止原因、真实单位和复权记录、14:30 PIT/OOS、本人 Codex/费用任务、用户 E 盘 ACL。不得把 CI 成功解释为这些已经通过。

按 CODEX_RECEIVE_V106_20260915.md 接收；逐项状态见 POSTDEPLOY_CLOSURE_20260915.md。
