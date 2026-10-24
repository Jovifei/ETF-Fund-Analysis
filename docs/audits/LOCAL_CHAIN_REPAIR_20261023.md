# 本地链路修复候选：2026-10-23

基线1a4b6652f49c412145d12812fa02820ba0a80991。Jovi明确授权独立分支先测后修网站读超时与收盘日线失败，不自动部署。原目录用户修改、F盘数据/配置、服务器搬迁/备份与相关服务保留。

## 原始观察与复现

Jovi正常登录后总览决策板/板块/上下文超时，一次只读重试无恢复，后续出现http_502；health200不等于消费通过。

读取指定generation时，原实现先加载并验证所有保留包；保留20代而解析缓存仅2代，重复冲刷。5项RED分别覆盖字符串/整数sequence、完整/短hash及缺失代。修复只按不可变文件名预筛候选，再执行原完整内容/哈希/歧义验证，不从文件名推导可信内容，也不退回latest。

离线使用真实公开展示包构造20个保留代：冷读取13.397670秒→0.625235秒，5并发12.705884→0.662558秒，完整校验20次→1次。返回SHA256均为2690b0fc887ad16310aa0eaeb53585bcd185edd17733461ee7bdd23d8761b71d。代数量是受控回放，不是服务器负载或公网时效验收。

## 收盘日线

只读研究运行审计显示15:15两次完成0/34、16:10两次完成3/34和6/34；腾讯候选为target_date_missing，AKShare为price_only_units_unverified。原始失败、partial、量额资格不改写。

本机安装AKShare1.19.1的腾讯历史SDK在同年使用固定年度查询和r参数，存在晨间响应缓存复用风险；本地离线实际SDK请求捕获已RED复现。它不是实际第三方延迟的唯一原因证明。

仅在既有隔离SDK子进程、请求上海当天日期且已过15:15结算截止时，对SDK原腾讯历史URL克隆参数更新r缓存键。克隆函数命名空间，不全局猴补requests；继续使用原SDK解析、单位、allowlist、超时、子进程回收与响应大小限制，不直接新写抓取接口。

现有显式retry_history_once公开源策略允许target_date_missing有且仅有一次重试，保留第一次ProviderAudit；限流/许可/凭据/格式拒绝仍不重试。第二次仍缺目标日期继续失败，不将旧日线改为今天。操作策略升为daily-batch-v1.0.5-audited-target-retry，数值公式/策略阈值与资格不变。

## 实际验证边界

- 子任务读取路径相关138项通过、日线相关92项通过，分别留存日志，不将重叠覆盖相加成全量。
- 父流程独立组合重点验证49通过；包含缓存别名/缺失代、实际SDK离线传输、截止/其他日期、单位、一次重试和原审计。
- 最终固定源码完整pytest、compileall/Node、独立交叉复审和网页GPT复审：冻结后执行并另行记录真实结果。
- 真实Provider采集、生产数据库写入、服务器部署均未执行；不得声称线上超时或真实收盘已修复通过。
- 两交易日观察Disabled，尾盘120秒、正常用户同代消费、手机、许可/PIT/OOS与校准仍独立待验。

脱敏证据在E:\Claude_allow\Download\ETF-chain-fix-20261023：web-read目录、bars-operational-receipt.json、bars-green-final.log及parent-focused.xml。Hub revision查询Win10061失败，未发送或自动重试。

文档精简在独立codex/docs-consolidation-20261023，不把文档清理混入业务修复。main不变，任何合并/部署须按Jovi实际条件。

## 必要依赖安全修补

CI实际发现Vite7.3.5命中GHSA-587h-7wmj-h5pm高危（上游公告：https://github.com/vitejs/launch-editor/security/advisories/GHSA-587h-7wmj-h5pm）。Jovi另行明确授权同大版本最小升级到7.3.7，不降低门禁。package-lock仅根Vite声明与node_modules/vite条目改变，其余锁定包原样。

隔离安装ignore-scripts，初次npm ci因ECONNRESET失败保留日志；使用既有缓存重新执行成功。安全审计高危/严重均0，仍有2中危/1低危独立保留；205项Vue单测、TypeScript和生产构建通过。旧固定59fbb13的后端全量在独立未改工作树运行，后继补丁不改backend/scripts或测试；新SHA的精确CI另行核验，不冒充新SHA已本地全量通过。

## 2026-10-24 可信接收与上下文整合

网页GPT PR53 f89b382与本地版本化上下文整合为f6d0d332ab8bd27f34cb573b31a141f32cc57bac。后继独立复审以真实签名HTTP复现“latest缺失、previous保留时接受未知旧序号”（RED1、空存储正例1PASS）；两行一致性守卫冻结于ee6513a2fa8d4b60ad516abf9a9b6f250efd27be，135项组合测试通过。历史接收身份随latest原子提交，未采用增加状态的accepted.json候选。

上下文合同local-display-context-read-v1区分采集失败/部分/沿用/未发布、历史身份与过期；来源/生成/刷新/读取时间分开，不以读取时钟重写as_of。保留旧列表接口，GET不调用研究SQL/Provider；本地模式不提供未发布的指数历史/云端写操作。完整manifest身份、HMAC、现行身份、时间和SyncDomain峰值门禁保持。

实际本地：135项接收/上下文组合、228 Vue、类型/构建/静态、44隔离Mock smoke、18窄屏与6认证回放通过。后端守卫未改前端src/依赖；认证夹具使用真实版本化合同，补全部时间/状态断言与任何workspace POST检测；窄屏及首页测试使用现行1/3/7/20/60并验证7日保留。旧horizon5、旧fixture与容量合成余量失败均保留，不增超时、不跳断言、不降生产64MiB/320MiB门槛。

最终完整后端仍在ee6513a固定源码运行；此前f6本地49%中断没有完整结果，r2又因新P1被明确取代，均不标PASS。f6的GitHub完整ci/PG/Windows/followup已通过，但workspace因旧认证夹具失败；最终提交必须重新核精确CI和网页GPT复审，才能按授权合main。本轮未部署，正式任务/数据/Owner修改保持。真实收盘34覆盖、正常公网同代消费、自然两日/云端零增长、手机和资格仍独立待验收。

集中材料：E:\Claude_allow\Download\ETF-chain-fix-20261023，receipt-v2/context-v2/auth-final-20261024-1/responsive-current与最终完整测试收据。最初本地auth从根目录启动导致runtime身份未核，已加ENV_UNQUALIFIED注解，不能作为当前源码回归；正确frontend目录复现的CI同类RED及GREEN独立保留。

### Windows完整回归发现的测试启动边界

ee6513a完整本机后端已结束：2638项=2613通过/24跳过/1失败，1242.831秒JUnit，进程exit1且backend_scope_unchanged=true；唯一失败test_paddle_response_then_sleep_worker_is_cleaned_up返回unavailable，原断言未记录reason。原日志/XML保留，不能以单独重跑通过覆盖。

独立实际spawn+原2秒adapter的6对对照：原重模块worker5/6完成、1/6明确timeout，耗时1.422–1.922秒成功窗；仅time的轻量worker6/6完成，0.188–0.562秒，12次均无新增子进程。单独导入探针测重测试模块1.610秒、启动到响应1.813秒；轻量模块启动0.250秒。原完整失败缺reason，不能追溯断言那一次一定为timeout；该机制已经实际复现。

最小修复仅移动测试worker至backend/tests/_ocr_workers.py，保留相同发送/睡眠、真实spawn、2秒期限及before/after无泄漏断言，并使失败消息携带合成result.reason。OCR生产、模型、权限、策略和任何超时均不变。实际OCR模块69项=67通过/2跳过，0失败。材料ocr-ci-review/results.json、import_probe.json及holding-module-green.xml；两项先前不完整额外导入探针未用于通过结论，后续独立探针停止/无新增子进程已核。最终完整测试与精确CI仍需绑定新提交。

网页GPT同一普通Chat已收到固定GitHub复审包；之后一条全量失败通知遭Too many requests，NOT_SENT，不冒称已送达/已审。等待通道恢复后集中回传最终GitHub收据；本轮仍不合main/部署。
