# 下一阶段实施计划：S8-F0证据对账 + S2降级状态可读化
## 与长期路线图的关系

本计划按 docs/PROJECT_MASTER_ROADMAP.md v2执行。近期业务优先级是S8-F0真实分钟量额数据可行性；S3/S4当前已部署版本的独立接收并行。WU1属于S2“详情与研究解释”的有界批次，不代表S4完整完成，也不跳到S5–S7扩张。

本阶段按三个工作单元推进：
- **WU0：先对账数据结论和产品决定。** 有证据则完成F0-10交接；没有证据则继续长期计划中的F0调查。
- **WU1：将已有研究可用性、降级和阻断原因诚实展示。** 不改计算、策略和资格，可在WU0调查期间有限并行。
- **WU2：接收当前已上线图层/份额及发布证据。** 与WU1并行，发现合同差异单独列出，不暗中改变结构路线。

交付效果：用户能够看懂“哪些研究功能有可读数据、哪些受限以及为什么”，同时项目有可追溯的数据路线结论和当前上线版本接收记录。此计划只授权列明范围；S8-F0成功不等于统计有效、数据资格通过或actionable晋级。

## 0. 开工时先核对事实

审核时（2026-10-02）main为8b6d028且工作区干净；STATUS/HANDOFF和进度仍记录F0调查待执行。原稿声称F0已结论、owner拒绝采购并永久定型为价格看板，但当前仓库未找到相应结论收据或决定引用。**不得把原稿叙述当作已验证前置，也不得否定可能存在的仓外最新证据；先对账。**

原稿中的“Tushare为唯一路径、约2000元/年”没有本计划可核对的当前官方证据，不作为已知事实或购买依据。本阶段不新增采购；既有明确决定若已存在，引用后沿用，不重复问批准。

开工重新读取：
- STATUS.md、HANDOFF.md、docs/PROJECT_MASTER_ROADMAP.md；
- docs/PROJECT_PROGRESS.json及PROJECT_PROGRESS_MAINTENANCE.md；
- docs/planning/S8_F0_DATA_FEASIBILITY_SPIKE.md；
- docs/audits/CURRENT_PRODUCTION_IDENTITY_20261002.md；
- 受影响模块当前代码、测试、版本及AGENTS.md。

不硬编码此审核时的SHA/行号为未来基线。Git main、部署源码、文档提交、schema、测试收据分别记录。63c426a/f0/v109是既有只读观察，不由本次计划证明仍是最新或已经完整验收。

## 1. 执行位置和授权边界

从核对后的main建立项目内干净隔离工作区，建议：
- 分支：codex/s2-availability-stage-20261002；
- 路径：E:/project/ETF-Fund-Analysis/.local/s2-availability-stage-20261002。

已存在合适工作区则核对后复用。检查主目录脏状态，不reset/clean/stash，不覆盖其他Agent改动。执行器可自行确定常规分支和展示布局，无需把技术选择交回owner。仅真实缺失的人类预算、许可、权限或产品方向决定才提出。

本次仅审核修改计划；本地Codex没有执行WU0探测、WU1代码或生产发布。后续执行者依照下列验收条件推进并回传证据。

## 2. WU0：数据路线结论与交接对账（先做）

### WU0-1 查找并核验现有F0证据

向已有执行产物索引查找，不索取密码/Token、读取.env或翻含凭据的聊天记录。结论至少绑定：
- 来源、接口能力、调查日期、合法访问条件及范围；
- 标的/周期/字段覆盖，5m与15m原生或因果聚合的区别；
- volume与amount各自单位证据；源时间、获取时间与历史/PIT边界；
- 有界探测结果、失败原因、官方许可/费用资料；
- FEASIBLE / CONDITIONAL / NOT_FEASIBLE_WITHIN_SCOPE结论的适用范围；
- 若已作产品分岔，绑定明确owner决定的可核对引用。

缺证据写UNKNOWN/PENDING_EVIDENCE_RECONCILIATION，不能制造“不采购已批准”或“所有来源永久无解”。

### WU0-2 有证据与无证据的推进

1. 证据充分：将结论收据写入docs/audits，并在F0计划、STATUS/HANDOFF、总路线与JSON台账记录实际结果和范围。
2. 证据不足：按已有S8-F0计划开展1–2工作日有界调查，使用合法且已授权来源、Adapter和隔离环境；等待授权时间单列，不采购、不写生产。
3. 有条件可行且真需预算/许可决定：列具体选项与成本，请owner决定；不重复索取已经作过的决定。
4. 选择价格研究路径：明确“当前预算/访问条件下的产品能力边界”，不是S8整体完成。保留数据资格UNKNOWN、预测not_calibrated；将未来资格/OOS研究记录为独立未完成项。
5. 可行：先限定输入做最小资格与PIT/OOS基准，不需先做完所有UX/消息/组合功能。

**分钟量额不可行不等于日线量额必然缺失。** WU1按每个标的、周期和字段的当前证据展示，不能因F0结论全局屏蔽所有指标或永久改变五档研究评级。

### WU0完成标准

结论与决定有证据或明确仍待调查；长期台账与当前事实一致。WU1代码侧通过不能替代WU0完成。WU0不是“随意冻结全部验收分母”的文档操作；本批次范围可以冻结，历史大阶段须逐项映射后计数。

## 3. WU1：S2研究可用性和降级状态可读化

### 不变的核心合同

- 不修改指标公式/初始化、阈值、预测特征/标签、评级/仓位、价格口径或数据资格。
- canonical action、grade、grade_reason和数值输出保持既有含义；actionable=false，不把可读数据称为已校准或可操作。
- 缺量不补零，缺价格不伪造值，非实时不标实时；原始/研究价格错配不强行叠加。
- 不新增pattern_forecast调用/响应，不运行模型、Provider、重算或入队。
- 不改decision-read-v109-flow-share或数据库快照/schema；若实现确实需要修改这些，暂停该扩展并给出独立合同变更方案。
- 本次是详情响应/展示的可观察变化，不能因“只读”排除发布。通过测试、GitHub和所需阶段复核后按既有授权部署，并做真实用户线上验收。

### B1 支撑压力：区分计算可读性与叠加限制

主入口为backend/app/workspace/read_model.py::instrument_detail()。当前availability有instrument、price、history、price_basis、indicators、volume、forecasts、decision八项；新增support_resistance后为**九项**，不是“全部八项”。

只复用现有support_resistance、qualification、input_availability及图表口径标志，不新增计算：
- 已有价格研究结果可读且qualification=price_only_research：可显示degraded及相应研究限制，不表示全部价格/结构能力合格。
- history_issue或快照损坏/合同问题：保留具体阻断优先级，不压成通用sr_input_unavailable。
- raw_overlay_allowed=false：优先呈现price_basis_mismatch等“禁止该叠加”原因；不能据此声称支撑压力完全没有计算结果。
- 真缺快照/未生成才用support_resistance_not_generated等明确缺失原因。
- payload因保护变为None时，availability仍说明为何隐藏，但不把不可信payload重新暴露来“保留原因”。

不承诺“缺合格量额时缠论必然可用”。持久化CZSC观测、简化结构和支撑压力是不同能力；WU1不改变其资格或替代关系。

### B2 预测：守住快照保护和周期维度

从现有ForecastSnapshot白名单化读取diagnostics reason；不把整个diagnostics_json透传，不把无快照臆测为feature_shortage。

原因优先级：
1. 晚于read_as_of、历史资格/版本/连续性或快照合同阻断；
2. 合同和时间可接受的已有诊断，如feature_shortage、feature_or_sample_shortage、history_too_short；
3. 真未生成/缺快照；
4. 原因未知。

feature_shortage只表示特征不足，**不能仅凭该字符串认定缺成交量/成交额**。中文显示通用原因；仅有明确missing_features/字段资格证据时细化到量额。

分别处理1/3/5/10期限，不能一个期限不足就把其他有效期限全部改成不可用。必要时在forecasts可用性下增加受控的by_horizon元数据，冻结其类型/测试；聚合状态不丢失已存在的期限差异。forecast_rows中“有对象但无可用数值”也不能自动标为有效预测。研究数值可读和calibration_status必须区分。

### B3 决策：只根据结构化证据说明受限

快照存在不等于研究动作可用。只从现有history/qualification/data_status等结构化字段推导受限说明：
- 明确量额资格问题时，增加针对该原因的可用性解释；
- 价格连续性、未来快照、版本、源失败或原因不明时保留各自原因；
- 不通过匹配中文grade_reason或仅判断grade=“数据异常”推断volume/amount问题；
- 同步更新decision_explanation.evidence_caveats，确保两处来源一致；
- 不修改grade、canonical action或策略评级，不能把普通price-only展示误判为资格通过。

### B4 契约版本和reason枚举

chart-read-v1.2.0属于chart_data，原稿指定升到v1.3.0的理由不成立：**只改详情availability时保持chart_contract_version不变**。

为新增详情可用性输出冻结独立版本：
- 根详情响应availability_contract_version = detail-availability-v1；
- TypeScript补对应可选字段，保持旧调用方兼容；
- support_resistance为新增可选ModuleAvailability；如需要by_horizon，明确独立可选类型；
- READ_MODEL_VERSION、指标/策略/预测版本不因纯说明变更而修改。若实际语义改动超出说明，按AGENTS另审并版本化。

可复用现有volume_missing_or_unverified、price_basis_mismatch及快照阻断码。新增候选包括price_only_research、support_resistance_not_generated、forecast_feature_shortage、decision_quantity_unqualified；只有映射条件确切需要才新增，前后端在实施前冻结最终白名单和中文文案。不能将所有None映射一个码。

本详情码与CZSC/M2引擎码分属不同合同，不改test_chan_m2_contract的错误码白名单来适配详情字段。

### F1 可用性面板

新增AvailabilityMatrix.vue或同等小型组件。明确展示九个受控模块的名称、模块对应状态、reason说明，固定顺序，不盲目遍历任意响应字段：
instrument → price → history → price_basis → indicators → volume → forecasts → decision → support_resistance。

面板标题和异常摘要常驻；正常项可折叠，异常/阻断项默认可见，用户可展开完整矩阵。兼容旧响应缺新增项，显示“未提供状态”而不是available。可读/研究/暂定/未校准/缺失/阻断文案明确，不能把aligned或active通用翻译为“可交易”。

空数据、错误、刷新失败保留旧快照、窄屏、键盘访问和状态文本可读。无效数字保持空态，不借reason面板生成计算值；使用Vue安全文本插值，不输出原始异常、URL、模型诊断或用户隐私。

### F2 映射集中化但不扩大重构

Detail.vue与新组件共享frontend/src/lib/availability.ts的受控映射。保留现有关键警告，去掉同一原因重复堆叠即可。decisionSummary/EtfChart有各自合同，本阶段只在确有共用且语义一致时调整，不开展全站重构。未知码给安全通用说明，不让未知字段自动通过。

## 4. WU2：当前S3/S4部署接收（并行、限范围）

查当前部署/迁移/衍生快照及GitHub来源，不能把旧3a/h9/9of13验收迁移到新版本。
- 核persisted Chan与simplified/prior-range回退是否区分来源、身份、方言和资格；不冒充canonical证据。
- 核ETF flow/share时间/单位和展示边界，不因已上线而计S1/S8 PASS。
- 核当前发布的备份、f0迁移与回滚兼容、v109衍生快照刷新；缺收据如实标待核对。
- 正常已登录会话做必要私有读检查；已有登录问题不重复问，不读Cookie/密码/Token，不建生产测试用户。
- 对读取路径新增调用/计算/写入风险做专项零副作用验证；同次GET立即前后比较，不比较登录前后。不把完整八项计数扩大到每个样式修改。

此工作单元首先产出接收矩阵/问题清单。修复关键身份/算法/Provider/schema合同的行为另列有界修复，不混入WU1说明变更。已有授权工程可推进，关键路线/资格分歧交远端或owner决定。

## 5. 实施和验证顺序

1. 记录实际SHA/分支、WU0证据差异及本批次可冻结范围；更新tasks/todo.md。
2. 先写失败复现/后端映射测试，再实施B1/B2/B3/B4；优先复用已有保护原因。
3. 跑受影响后端子集：test_v103_history、test_workspace_contract、test_display_qualification、test_quote_timestamp_gates、test_decision_board、test_postdeploy_pipeline，以及确实受影响的SR/forecast与Chan读取边界用例。
4. 前端先失败测试，再做组件/映射/类型；Vitest、typecheck、build及实际影响的页面/认证/响应式检查。
5. 根据后端共享读取函数的影响完成必要回归；项目要求pytest -q、compileall backend/app、Node syntax不遗漏。冻结后的代码没有新失败/改动，不重复无关跨平台digest或全套模型研究验证。
6. 测试临时目录必须遵守被测“私有配置在仓库外”合同；使用本轮独立、可写、仓外合成临时目录，不读真实.env，不修改安全规则来通过测试。Windows不适用的权限用例明确SKIPPED。
7. GitHub精确提交代码/测试/收据；按L1展示合同完成阶段复核，关键合同差异独立审查。
8. 依下节发布并正常用户验收，最终记录实际版本/差异、完成与阻塞项。

必须覆盖：
- 真实无数据、只有价格、缺volume但amount存在、反向缺amount、单位未证实；
- 特征不足但量额不缺、样本不足、未来/旧版本/无预测快照；
- 不同预测期限有不同状态；
- SR价格研究可读但raw叠加禁用、快照损坏不透传；
- 决策异常来自非量额原因，不能误贴量额码；
- Mock/历史/暂定/未校准不升级实时或actionable；
- 前端旧响应、未知reason、部分availability、刷新失败/移动端。

测试只断言真实映射与保护，不通过删除断言、改全局白名单或放宽source gate“转绿”。

## 6. 发布与线上验收（本阶段包含）

WU1是可观察的产品功能，需上线让owner验证。执行者沿用已有部署授权，不因每个小步骤重复问发布许可；新增高影响边界/真正授权缺失时才提出。

发布清单：
1. 精确测试提交与当前运行基线，说明本次不改schema、数值策略和Provider。
2. 生产变更前备份并验证，保留可执行回滚；复用仍适用于当前schema的恢复/回滚证据。发现版本兼容不确定则补演练，不把旧h9证明用于f0。
3. 构建审核镜像、发布API/前端受影响服务，保持凭据和运行配置，禁止资格或Chan激活。
4. 核health/static/auth、受影响详情接口和正常用户矩阵显示；需要衍生重算时仅用既有审计任务，纯详情说明不无故重算。
5. 失败回滚；记录源码/镜像/schema、时间、测试与UI结果。真实登录待完成时标PENDING，不伪造线上验收。
6. 同步总路线进度台账和最终收据，按阶段批次交远端复核。

无需为没有数据库变更的展示批次重复完整migration/restore drill；需要的安全边界、备份与回滚不可省略。

## 7. 本阶段验收与交接

- WU0结论和产品决定有来源；缺证据保持待对账，不写永久产品定型或S8完成。
- WU1九项矩阵与每期限原因可信，不混淆“有快照”“研究可读”“已校准”“可操作”。
- 原grade/canonical action/数值公式/策略与快照版本不变，actionable=false；chart_contract_version未因详情说明被误升。
- API新增可用性合同有独立版本，前后端白名单、保护优先级和中文一致。
- GitHub代码与测试可核对；正常用户可以在部署后查看新增功能，或明确记录具体线上待验收项。
- WU2接收结论与发现独立列出，不把展示完成算整个S3/S4或数据资格通过。
- 更新STATUS、HANDOFF、PROJECT_PROGRESS.json，运行进度生成器及--check，回传阶段收据。
- 按已授权AGENTS项目Hub约定，先取实际worktree/branch revision再生成事件，上报实际成果；不改变Hub目标/路线，不附凭据、原始敏感日志或聊天全文。

参考改动点：backend/app/workspace/read_model.py；现有SR/forecast/decision服务只读合同；frontend/src/views/Detail.vue、components/AvailabilityMatrix.vue、lib/availability.ts、lib/types.ts及相应测试。此列表是有界范围，不要求改全部参考服务文件。

## 8. 范围外

本阶段不采购数据、不恢复actionable、不改评级/指标/预测算法、不新增pattern_forecast、不启用Chan/模型/自动交易，不实施S5–S7扩张。S4图层/结构算法的修复在独立接收发现和正式范围明确后开展，不能借“数据可读化”加入第二套未审结构语义。

## 审核记录

2026-10-02本地Codex对照长期路线v2与当前main审核，直接修订本文件。已纠正：未证实F0和owner决定、脏main假设、八项/九项计数、feature_shortage等于缺量额的误推、grade异常误归因、Chart/Detail版本归属、只读不部署及常规选择反复确认。此审核不等于产品实现、数据调查或生产验收已完成。
