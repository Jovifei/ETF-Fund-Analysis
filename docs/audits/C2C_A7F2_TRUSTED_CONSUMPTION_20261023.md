# c2c_a7f2 — 实测与审查收据

本收据区分远端隔离实测、GitHub CI、生产与人工验收。交接见 [阶段交接](../handoffs/C2C_A7F2_TRUSTED_CONSUMPTION_20261023.md)。

## 来源与可重复性

GitHub插件读取 main 1a4b6652f49c412145d12812fa02820ba0a80991 / tree ba3e9af620315cca7fb5b59cd618f95922534bd8。由同仓库 workspace-ci run 39877690392 的 artifact 12469351203 获取源码归档，归档SHA256独立核验为 `87456f54b62974bfa3ee5f757be38e4821a050d8d5f86ffddc113e910368f66a`，tar的commit标识为该基线。隔离环境 Python3.13.5、Node22.16.0，不冒充项目标准Python3.12/Node>=22.18或Owner电脑。

测试先行真实提交 8ee2daacb2066fb541cddd3524c0cb99b825ad3b。初始11项测试在未修复源码上实测10失败1通过（0.417秒）：未知历史身份未拒绝、固定代解析无关包及缺少状态消费合同。8代/8并发的序号和hash读取分别观察到43/49次包文件读取；这是合成调用计数，不是生产p95、内存或延迟SLO。

## 本轮实际执行

| 检查 | 实际结果 | 边界 |
|---|---|---|
| 初始失败测试 | 10 FAIL / 1 PASS | 基线，修复前；包含新增消费合同的缺失 |
| 最终聚焦三个文件，排除两个API导入测试 | 28 PASS，2 deselected，3.013秒 | 原仓库conftest，合成文件；不是全后端 |
| receiver_safety 原有78项 | 68 PASS / 10 FAIL | 10项均在导入pwdlib时报ModuleNotFoundError；整个文件不标PASS |
| 全量 pytest -q --maxfail=1 | COLLECTION_ERROR | 首个account_self_service导入缺pwdlib；并未运行完整测试体 |
| python -m compileall -q backend/app | PASS | 当前隔离代码 |
| node --check backend/app/static/app.js | PASS | 语法检查，不是浏览器验收 |
| 直接执行修改后的api.ts，Node内建test | 4 PASS | 超时/主动取消、解析期间注销、晚到401、同源GET；不是Vue/typecheck |
| git diff --check | PASS | 隔离差异检查 |
| Vue单测/typecheck/build/认证浏览器 | NOT_RUN locally | npm依赖安装失败；不降低依赖版本、替换鉴权或跳过门禁伪造通过 |
| 生产/Provider/手机/自然两日 | NOT_RUN | 无本轮操作授权或真实验收环境 |

主要复跑命令（在已安装项目依赖的固定SHA工作树）：

```sh
python -m pytest -q backend/tests/test_local_display_consumer_contract.py backend/tests/test_local_display_bundle_cache.py backend/tests/test_local_display_read.py backend/tests/test_receiver_safety.py
python -m pytest -q
python -m compileall -q backend/app
node --check backend/app/static/app.js
npm --prefix frontend test
npm --prefix frontend run typecheck
npm --prefix frontend run build
cd frontend && npx playwright test --config playwright.auth.config.ts local-display-consumption.spec.ts
```

远端聚焦实际命令使用 `-k 'not test_api_'`，两个API测试不能混入28项通过。隔离pip安装也受可用包源限制，没有修改项目依赖。Node版本低于项目声明，不据此宣布标准环境通过。受控浏览器测试代码使用真实测试登录与路由模拟包；即使将来通过也不是生产行情或真人验收。

原始运行证据的SHA256（本机临时收据，不含私有数据；哈希本身不代替复跑）：red.xml `a0c21062d15d2ce1f44b80112e714f101c2fb746c487bd941612be10fd04257b`；focus-final.xml `a1298ee3155a36b8b708ae64c0a628e8cb898d4bd5a75bd2c213a0ebe8313a97`；receiver.xml `4ee7787beebd06e15d026bbcc6b8e0c82ca68dc536eda65cf383fb19bd8f91c6`；full-attempt.xml `be0946c604cf9939eff1b587bbec18b371158c8ee0ee253bf5d02a4e0b830703`；api-runtime.log `6e54b29a49b1c3e7707d54641d7909d749f218e29e3a6fe5d7a5757a0ffe0737`。

## CI与复审边界

既有ci/workspace-ci/audit-platforms会由push/PR触发，工作流未修改。基线ci run39877690386成功、audit-platforms39877690358成功，不证明本分支通过。基线workspace-ci39877690392在依赖安全门失败，其归档npm审计记录含Vite高风险；这不是本轮新增缺陷，也不能绕过。最终提交CI状态以PR #53精确SHA的实际Actions/jobs回读为准，本预提交收据不预写成功。

最终差异审查重点：history与latest同次原子提交，失败无新证明；proof缺失/裁剪/损坏保守拒绝；current/previous及未知资产保留；指针峰值/字节上限；目标内容完整性与别名歧义不放宽；GET不引入Provider或研究写库；超时仍20秒且会话隔离保留；没有修改策略/Provider/依赖/工作流/账户持仓或生产文件。独立人工/本地审核仍PENDING。

## 开源设计核对

2026-10-23查阅DiskCache官方文档 https://grantjenks.com/docs/diskcache/ 及 https://grantjenks.com/docs/diskcache/tutorial.html 。其事务原子性与缓存淘汰/持久索引分离思路可参考；官方标注Apache2许可。决策是不引入或复制第三方源码：现有原子指针已能承载小型有界接收证明，增加数据库缓存反而引入迁移、写入GET/LRU及新的依赖边界。保留所有现有NOTICE，未把软件许可当数据源许可。

结论：已实现有界可靠性阶段并有真实红绿证据；完整CI、标准环境前端/鉴权测试、组合分支与真实线上验收未完成前，仍非可部署批准。source/license/PIT/OOS UNKNOWN、actionable=false、not_calibrated。
