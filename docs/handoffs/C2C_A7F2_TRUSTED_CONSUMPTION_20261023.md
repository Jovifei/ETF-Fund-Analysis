# c2c_a7f2 — 可信接收与同代消费阶段交接

状态：IMPLEMENTED / INDEPENDENT_ACCEPTANCE_PENDING。这是源码候选，不是生产发布或资格批准。

基线：`1a4b6652f49c412145d12812fa02820ba0a80991`，tree `ba3e9af620315cca7fb5b59cd618f95922534bd8`。分支：`codex/c2c-a7f2-trusted-consumption-20261023`，PR #53。首个真实失败测试提交：`8ee2daacb2066fb541cddd3524c0cb99b825ad3b`。最终 SHA/tree 应读取此文件所在的 GitHub 提交及 PR 精确 head；文档不能自引用尚未生成的提交哈希。

## 授权与取舍

Jovi 在基金决策项目同一会话授权先前文件级范围及 GitHub 插件，仅限 Jovifei/ETF-Fund-Analysis；远端主实施，本地独立接收固定 SHA。本轮选择 S9/S1 的可信接收与读取可靠性阶段，先于 S8 算法扩展：当前已有接收身份和多代读取失败复现，而真实来源许可/PIT/OOS/校准仍未取得资格。没有扩展 Provider、策略、生产或账户权限。

本地工作区经唯一 ETF C2C 连接独立核实 main@1a4b665；tasks/todo.md、tasks/lessons.md 及未跟踪的 REMOTE_LONG_STAGE_20261023.md 保持 Owner 修改。本实现发生在通过 GitHub 插件取得的隔离源码副本，不在 Owner 工作树执行命令，不读取私有库、凭据或持仓。

## 已实施的连续工作包

1. `local_display_read.py`：接收历史 `local-acceptance-v1` 随 latest 指针原子提交，绑定精确 sequence+bundle_id；未知旧序号、同序号异内容及孤立缓存均不能冒充 already_accepted。记录上限256且指针上限64KiB，计入既有磁盘峰值预算；失败不产生接收证明、不提升历史包。旧指针只迁入已验证的 current/previous，不能推定其余历史缓存曾获准；历史文件仍可读取。证明被裁剪后保守拒绝恢复，不能把此有限台账称为永久审计档案。
2. 固定 generation 先以文件名筛候选，再做内容/完整身份/歧义验证；缓存键加入 ctime 并复核读取期间文件身份。多个历史代不再被每个固定代请求全量解析；不存在的代不回退最新。此项与另行 PR51 的候选筛选逻辑一致，不宣称重复发现或替代其日线修复。
3. 新增 `local-display-consumer-v1` 读取元数据，保留代号、过期状态、可选刷新失败/同日沿用原因；旧 bootstrap 列表接口兼容。板块宽度仅映射既有计数字段，缺值仍为 null，来源未知不编造。API 缺本地数据时不再查询云端证券目录来猜原因。
4. 总览和详情按实际 local_bundle 模式隐藏云端采集/历史准备/未发布的分钟与指数OHLC操作，明确本机更新和主动读最新。已有固定代和图表时点匹配保持。查询合并同URL并发刷新；URL变化仍取消旧请求，旧响应不得覆盖新代。真实超时与主动取消分开，默认20秒不延长，鉴权/会话epoch/CSRF不放宽。
5. 增加接收负例、故障恢复、字节预算、多代并发、API无数据库回退、前端取消/切代及受控认证回放测试。已运行与未运行结果见对应审计收据，不能将测试代码存在当作通过。

Bundle线协议和内容验证仍为 local-display-v2 / local-display-validation-v2.3；本轮只新增接收指针和消费视图版本，没有变更指标公式、数据单位、预测期限、评分或配置哈希算法。UNKNOWN / actionable=false / not_calibrated 保持。

## 验收与接收

先核 GitHub ref 和精确 SHA/tree，再在独立工作树接收，不 reset/clean/stash Owner 修改。运行完整后端、Python编译、静态JS、前端typecheck/unit/build与受控认证浏览器专项；命令及环境限制在 [审计收据](../audits/C2C_A7F2_TRUSTED_CONSUMPTION_20261023.md)。CI 必须绑定实际提交/merge候选，不能继承基线绿灯。未通过依赖安全门不得绕过或写成全绿。

正常生产登录、真实收盘刷新、自然触发、两个真实交易日、本人手机/DPR及长期观察尚未验收，本次不部署。合成浏览器登录仅使用既有测试账号，行情响应为受控路由回放，不是真实生产消费。当前生产SHA未重新确认。

## 并行变更及回滚边界

本轮发现 PR51 head e121b13f4f1ee2f6dae00baa12ce3a5d22571ecd（读取优化、Provider日线修复、依赖升级）及其上 PR52 head 9aa1f49bb871690c5676358bf064947287c4459e（文档精简）。只读过实际PR与读取筛选差异；未合并、覆盖或继承其测试结论。后续组合接收需保留两者并重新验证组合SHA。本分支不纳入其Provider、依赖升级或删除20份文档。为避免覆盖并行文档整理，本轮事实单独记入本交接和审计，主STATUS/HANDOFF/进度台账未假写阶段PASS，整合时从本收据对账而非覆盖Owner版本。

没有数据库迁移、生产写入或部署。回滚源码不会删除用户数据；已发布指针新增字段对旧Reader可读，但旧接收器缺少精确历史门禁，因此不能把降级旧写入端当成等价安全修复。保留current/previous、备份和新指针；任何生产切换与回退另需批准和精确收据。

项目Hub本机Windows报告命令本轮 NOT_RUN / NOT_SENT；远端不能声称代本地调用。下一步是固定SHA的独立接收与组合CI，不是扩大算法或数据资格。
