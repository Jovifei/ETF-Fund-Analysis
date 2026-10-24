# 可信接收与上下文整合验收

状态：IN_PROGRESS，未合main、未部署。仅记录真实完成项，不继承历史发布/旧SHA完整测试。

当前源码：bdb556f9c60254b2e8e866f256386b062e2ab7ab；tree 4e0ce8c0f90f6cfb3552b026c829046821e8ccc2。业务源码固定ee6513a，测试夹具后继bdb556f，frontend业务源码与f6d0d33一致；父版本fe0a615与网页GPT PR53 f89b382在独立分支整合，接续修复复审发现的latest缺失边界。main仍1a4b665；PR51为源码，PR52为文档。

## 实现与验证

- 服务端仅凭完整sequence+manifest digest的有界接收历史认可旧包；记录随latest原子提交。任意旧文件/签名/较小序号不等于接收证明。legacy current/previous仅证明自身；裁掉的证明不从缓存重建。256项/64KiB指针上限、现行身份/有效期和SyncDomain峰值计费保持。
- 对照候选的独立accepted.json方案未采用，避免增加原子状态；候选/失败材料保留。真实历史恢复跨重启/过期/回收、未知身份、损坏、符号链接、原子失败与预算19项独立行为检查通过。
- local-display-context-read-v1区分失败、部分、沿用、未发布及批次不可用；generation、来源日期、生成/刷新/读取时间分离；历史身份与过期独立。不以读取时钟刷新as_of。
- 本地模式不提供缺失的指数历史/云端采集动作；ETF代理导航、数据库/Mock演示历史保留。主动reload重发GET，自动refresh才合并在途同URL请求；会话与晚到响应隔离保留。
- 初轮整合70项中4FAIL（原因枚举、直接调用Response参数、两项旧容量夹具），及前端重复状态提示/类型错误保留后修复；整合后70后端专项与228Vue、类型/构建/静态通过。
- 44项隔离Mock smoke通过，旧horizon5改为现行1/3/7/20/60并验证导航后7日选择保留，未提高超时或删断言。
- 容量测试改为计入有界历史元数据的合成预算，显式3代强制旧包回收；os.replace前核实际磁盘+held峰值，每次不得超限，current/previous保留。生产64MiB/320MiB限制及不足预算拒绝负例未改。
- 135项接收/上下文组合、18项窄屏及6项认证回放已通过。认证新fixture含完整版本化时间/状态合同，禁止本地无历史卡片动作与任何workspace写入；旧RED保留。最终ee6513a完整后端与精确CI待结果；不代表生产验收。

材料位于E:\Claude_allow\Download\ETF-chain-fix-20261023，包括receipt-v2、context-v2、integrated-first/targeted、pytest-f6d0d33、smoke-f6d0d33和auth-red-f6d0d33。源/测试与候选可从GitHub固定提交独立读取；私人数据/配置未上传。

网页GPT最终复审待连接恢复与固定证据提交。真实收盘完整34覆盖、公网正常用户同代消费、手机、自然两交易日、云端零增长、PIT/OOS/许可分别未通过。保持UNKNOWN/actionable=false/not_calibrated，无自动交易。

## 整合后独立边界复审

签名HTTP先接收2/3后仅移除夹具latest，保留previous=2，旧实现会错误接受未知新鲜seq1；RED1/空存储正例1PASS保留。Store补两行一致性守卫，缺latest而有previous时拒绝激活；不从缓存猜接收历史，135项组合GREEN。真正空存储首发保持。

此前f6完整本地测试49%执行通道中断，没有XML/退出结果；r2因上述新P1明确取代并留痕，不标通过。当前最终完整后端由独立证据驱动运行ee6513a，提交ba86baf只再改测试/忽略规则/文档，backend/scripts/pyproject与该固定源码相同。CI命名postdeploy仍只是测试，本轮无服务器部署。

## 完整Windows结果与测试夹具边界

ee6513a完整2638项=2613通过/24跳过/1失败，1242.831秒JUnit；失败为旧OCR清理夹具status unavailable，原测试未记录reason，单项重跑通过不能覆盖该全量失败。独立6对真spawn对照复现重测试模块1次timeout，轻量worker6/6且12次均无新增子进程；独立导入1.610秒对轻量启动0.250秒，历史那次具体reason仍未知。

bdb556f仅将合成worker移到time-only测试模块，保留真实spawn/原2秒/相同发送睡眠/清理断言，添加reason诊断。OCR模块67通过/2跳过。backend/app/scripts/pyproject/frontend业务与ba86baf无差异；最终完整bdb556f运行，不把67局部通过写成完整通过。原失败、首轮不完整探针、后续无泄漏探针与全部中断记录保留。

复审通过同一基金决策普通Chat沿用户授权的会话通道发起，仅GitHub固定源码；后续一条失败通知429未送达，最终复审仍未确认。不得据此合main/部署。

清理例外：context_status_pipeline子任务报告删除误建frontend/frontend/node_modules链接被自动审批以blocked by policy拒绝；保持原链接、未重试，不作为源码提交或删除共享依赖。
