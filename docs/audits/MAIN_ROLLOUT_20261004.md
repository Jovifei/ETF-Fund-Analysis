# 发布与新候选接收 — 2026-10-04

## 已上线版本
- 上线时点：2026-10-04 00:56:03 上海（UTC 2026-10-03T16:56:03Z）。
- 精确源码 ef287c06b4bd6b8ecd507149a0a0d7bd398e4162，tree08b61f228d4ff108993efbd9649fd33aa79634e3。
- 三服务镜像 f2b943564736d1e1b6994e5777c834383452a9515cc8f6d3990341b9d4f64bc5。API/worker healthy，scheduler Running；schema f0e1d2c3b4a5与新镜像head一致。
- MARKET_PROVIDER=public_composite、MINUTE_BARS_ENABLED=false、ALLOW_MOCK_FALLBACK=false、AUTH_ENABLED=true保持现状；本轮无配置/业务表直接写入、手动刷新或资格晋升。
- CI镜像ZIP/内层SHA、源码标签/tree、备份SHA/gzip已核验，旧镜像与原六份Compose配置保留，切换脚本具备三服务运行/健康和自动回滚门槛。详情见前一收据MAIN_INTEGRATION_RELEASE_20261003.md。
- Jovi授权仅Docker构建缓存清理；实际回收6.076GB，镜像加载后可用约6.4GB。数据库、备份、卷和旧回滚镜像未删。
- 当前公开入口/资产及鉴权边界验证PASS。/matrix与/classic/etf-board按源码合同307跳转到/#etf-decisions；旧通用脚本将跳转视为失败，其失败文件保留，不冒充PASS。当前合同专用审计live-current-contract-audit.json PASS。
- 近5分钟Provider审计汇总为空，只表示无该窗口记录，不作为真实Provider PASS。

## 手机和资格
- 识别到真实OnePlus7Pro GM1910；自动启动手机Chrome被自动审批拒绝，仅返回blocked by policy，未给具体原因，未绕过。
- Jovi回复“暂时无法验收”；实体手机/私有真实详情/R10仍NOT_RUN或PENDING，不能把Chromium390px模拟当实体手机PASS。
- real_data UNKNOWN / actionable=false / prediction not_calibrated保留。

## 新增v110候选（未上线）
- 发布期间fetch发现8c62d70；三条该分支精确CI已独立核实success。
- 已合入main01ea77e，Windows测试兼容修复5c1e2a4；三业务源码与8c62d70一致，不新增迁移/配置。
- 旧v109看板将因v110版本失配显示数据异常，须受审计刷新才能生成新v110。已明确告知，Jovi选择“先合入并测试，暂缓上线v110”；没有上线v110或触发刷新。
- Windows聚焦首先90通过/1失败：网络禁用夹具误拦Proactor wakeup socket；预建loop并复用TestClient上下文，双网络guard及全部HTTP/数值/快照断言保留，补负控。91聚焦PASS，最终负控单测PASS，独立源码审核PASS。修改仅测试文件。
- 首次v110完整回归在确认上述确定性失败后中止，不作为PASS；修复后的完整回归进行中。前端与已验证ef287c0完全无差异，不重复此前116/类型/构建/浏览器5项验证。

## v110本地终态
精确代码/测试5c1e2a4504bba71f20d02bcf1e2f86263f24d121最终完整pytest退出0：1576收集/1553通过/23既有条件跳过/0失败/0错误，627.224秒；跳过身份对照上批无变化。JUnit E:/Claude_allow/Download/etf-main-v110-final-20261004.xml。compileall/Node/progress check及diff check通过；业务源码对照8c62d70无差异。5c1e2a4的workspace-ci37139304064、audit-platforms37139304072成功，完整CI37139304073仍运行；不声称全部精确CI闭环。Jovi暂缓v110上线与刷新，当前线上仍ef287c0。
