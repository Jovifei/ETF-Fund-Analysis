# 可信接收与上下文整合验收

状态：IN_PROGRESS，未合main、未部署。仅记录真实完成项，不继承历史发布/旧SHA完整测试。

源码：f6d0d332ab8bd27f34cb573b31a141f32cc57bac；tree f52c2900e7056e42e83cc8699880f28be03f7522。父版本fe0a615与网页GPT PR53 f89b382在独立分支整合。main仍1a4b665；PR51为源码，PR52为文档。

## 实现与验证

- 服务端仅凭完整sequence+manifest digest的有界接收历史认可旧包；记录随latest原子提交。任意旧文件/签名/较小序号不等于接收证明。legacy current/previous仅证明自身；裁掉的证明不从缓存重建。256项/64KiB指针上限、现行身份/有效期和SyncDomain峰值计费保持。
- 对照候选的独立accepted.json方案未采用，避免增加原子状态；候选/失败材料保留。真实历史恢复跨重启/过期/回收、未知身份、损坏、符号链接、原子失败与预算19项独立行为检查通过。
- local-display-context-read-v1区分失败、部分、沿用、未发布及批次不可用；generation、来源日期、生成/刷新/读取时间分离；历史身份与过期独立。不以读取时钟刷新as_of。
- 本地模式不提供缺失的指数历史/云端采集动作；ETF代理导航、数据库/Mock演示历史保留。主动reload重发GET，自动refresh才合并在途同URL请求；会话与晚到响应隔离保留。
- 初轮整合70项中4FAIL（原因枚举、直接调用Response参数、两项旧容量夹具），及前端重复状态提示/类型错误保留后修复；整合后70后端专项与228Vue、类型/构建/静态通过。
- 44项隔离Mock smoke通过，旧horizon5改为现行1/3/7/20/60并验证导航后7日选择保留，未提高超时或删断言。
- 容量测试改为计入有界历史元数据的合成预算，显式3代强制旧包回收；os.replace前核实际磁盘+held峰值，每次不得超限，current/previous保留。生产64MiB/320MiB限制及不足预算拒绝负例未改。
- 最终完整后端、精确CI、认证受控回放与窄屏：待结果。认证回放初次失败已保留，不能标PASS；不代表生产登录失败。

材料位于E:\Claude_allow\Download\ETF-chain-fix-20261023，包括receipt-v2、context-v2、integrated-first/targeted、pytest-f6d0d33、smoke-f6d0d33和auth-red-f6d0d33。源/测试与候选可从GitHub固定提交独立读取；私人数据/配置未上传。

网页GPT最终复审待连接恢复与固定证据提交。真实收盘完整34覆盖、公网正常用户同代消费、手机、自然两交易日、云端零增长、PIT/OOS/许可分别未通过。保持UNKNOWN/actionable=false/not_calibrated，无自动交易。
