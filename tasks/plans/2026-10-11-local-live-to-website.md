# 本地真实计算 → 网站展示：执行方案（共同审议稿 v1）

状态：PLANNING_ONLY。本轮只制定方案；业务代码、任务、生产配置、数据及部署未变更。另一个执行 Agent 接手本方案。方案经 Codex 与基金决策网页端 GPT 独立提案、质疑、合并后定稿；文末记录实际审议意见，不能预先宣称共同批准。

## 1. 最终交付与基线

交付目标：真实行情从已允许的 ProviderAdapter 获取到 Jovi 本机，确定性程序按交易日定时计算现有研究/预测结果，通过已有网站 HTTPS 上传小型展示快照；正常登录的总览和 ETF 详情实际读取同一代本机结果。云端不再新增本阶段已迁移的原始行情和计算中间历史，仍保留账号、持仓、审计和必要有界展示数据。算法优化后续进行。

以下不是完成：Mock 成功、本地 HTTPS 成功、API200、收到文件、CI绿、仅新增旁路但正常网站仍读旧数据库。完成必须同时满足第9节所有真实链路验收。

已核基线：仓库 Jovifei/ETF-Fund-Analysis；实施 f514a6ec889d79109df12314947c8e77ed1948be，tree ba18dbfe20117afb46469f6b7b0b2b4a4fd150a0；文档收据0f8d16e724a5d3969172f3a565a4d87d1c7cc1c6，tree700d614bf885051194517f1529e59cec2c766ea2；Draft PR45。主分支是否改变、其他Agent是否推进和服务器实际身份须由执行Agent重新fetch/核验，不能按旧摘要部署。

既有证据仅属上述旧实施：1851后端通过/23跳过，198前端通过，四项PR工作流成功；Mock本地计算、一次性Windows任务、回环TLS/接收进程重启防重放已通过。不是本计划实现或公网真实行情证据。

当前明确缺口：shadow_export.local_settings/export_local/compute_local仅允许test+Mock；ROW_FIELDS没有完整forecasts/detail payload；shadow-display-v1仅日线；workspace/api.py总览/详情/图表仍走云端read_model数据库；没有正式公网部署/消费切换或云端任务退休。

## 2. 架构选择及数据摆放

```mermaid
flowchart LR
  P[已允许的真实Provider] --> L[本机独立SQLite与采集审计]
  L --> C[Python确定性计算]
  C --> B[不可变展示包与本机outbox]
  B -->|签名HTTPS| R[网站受限接收端]
  R --> S[有界快照store/latest指针]
  S --> A[认证展示API]
  U[现有云端账号与持仓] --> A
  A --> V[Vue总览与详情]
```

首期复用Python3.12、Node22.18+、SQLAlchemy/Alembic、SQLite、ProviderAdapter和现有算法。GPU和Codex常开不是执行依赖；Codex负责维护/诊断，Windows任务直接启动Python。不给LLM抓行情、数据库写入或算指标权限。不另建Prefect服务、Redis、Kafka、MinIO或DuckDB中间库来阻挡第一条链路。

建议本机专用根 `E:\ETF_Data\ETF-Fund-Analysis`：

| 路径 | 内容/权限 | 生命周期 |
|---|---|---|
| config/live.json | 非秘密provider、universe、时区、预算和契约配置 | Git外；秘密另由OS保护的运行配置注入 |
| db/research.sqlite3 | 原始行情、指标/预测历史、任务审计；不复制生产账号/持仓 | 本机单写者，WAL，在线备份API；不拷贝正在写的主文件当备份 |
| cache/provider | 必要原始响应，许可允许才留存 | 建议7天/1GiB上限，配置外置，达到上限暂停新缓存 |
| outbox | 不可变待上传展示包及回执 | 已接受+previous保留；待传最多3代/64MiB，过期包不补传 |
| logs、receipts | 脱敏结构化日志、输入/配置/源码/结果哈希 | 日志建议30天/256MiB；失败不删除 |
| backups | 本机研究库一致性备份 | 建议3份/2GiB，预算先测量，不自动删除用户其他备份 |

本机DB预算建议10GiB、剩余磁盘低于2GiB暂停新采集；均是首期工程预算而非已测结果，执行Agent先测真实范围并记录修订。历史扩容或换DuckDB在后续需要时单独评审。所有目录创建前检查解析路径、所有者标记、已有文件；不得替换现有研究库或使用生产连接串。

云端只保存：账号/持仓等原有私有事务数据；当前+上一代有界展示包及短期审计。K线展示仍需要有限OHLCV（初始日线最多250根/标的、派生周/月投影）和当前价格，这属于必要展示材料，不声称“云端完全没有行情”。禁止上传完整历史、供应商原始响应、训练样本、回测逐条记录或本机DB。新增行情历史表写入应为零。旧云数据本轮保留不删，故先证明增长停止，不能冒称磁盘立即释放。

初始接收request16MiB/store64MiB，沿用现有边界；记录真实压缩前字节、常驻RSS和latest/previous总量。超过上限不静默截断universe或扩大额度：先缩减未使用重复字段；仍不够提出经测试的分块manifest方案，完整校验后原子切换，不提前发布半包。上传压缩若引入须同时限制压缩前后大小、展开比和时间，避免解压炸弹。

## 3. 真实源、计算和时间合同

复用已有factory/composite/public_composite/akshare适配器。执行前以实际配置与数据探测确定首期provider；历史heartbeat曾用composite而旧部署出现public_composite，不能仅按旧文本写死。独立live profile显式选择现有允许provider；ALLOW_MOCK_FALLBACK=false、LLM/付费AI关闭。保留既有Mock脚本的guard，新增live入口及专用本机所有者标记，不把test/mock guard删掉即可称live。

真实非Mock不等于来源时间/复权/单位/PIT/许可/OOS都通过。为每类记录记录provider、trade_date、source_timestamp或unknown reason、fetched_at、adjustment_basis、units、数量/覆盖、缺口、延迟、使用许可证据引用。单位/复权冲突或未来时点阻断相关结果；源时间unknown不能包装为实时。网页能展示符合留存/展示范围的非实时研究结果，资格仍UNKNOWN/actionable=false/not_calibrated，不要求先完成策略OOS才能验收传输链路。

首期universe从独立非私有配置固定一组当前已支持ETF/LOF；先用510300.SH和512480.SH做端到端探针，最终验收须覆盖配置全部标的，不以两只试运行替代完整scope。代码可由Jovi指定，无需给producer读取网站持仓/用户权限。

初次抓足现有公式实际warm-up（420日只是Mock经验，真实缺交易日/暖机须按有效bars验证）；后续增量拉取已缺session和修订窗口，不能每五分钟重拉420天全量。重试只针对有界网络错误，限速、backoff、单源熔断沿用Adapter，不业务代码写网页URL。市场日历缺失先补可信日历或明确阻断，不猜交易日。

冻结一次input_snapshot_id/hash，所有研究/指标/forecast/board从同一数据切片生成，manifest写input/code/config/各模型版本及生成时间。采集、计算、导出、签名上传、回执、消费hash形成一条run_id链。相同输入重跑数值结果一致；系统时间/包装序号分开。单写者锁避免任务重叠和数据库边算边读混代；task审计保留failed/partial。

已有forecast horizon为1/3/5/10交易日；保留现有公式/字段，不把10日改名“一个月”。1日/5日可分别显示一天/一交易周研究预测；20日未实现则明确unavailable，本阶段不发明新模型。图表1d/1w/1mo是蜡烛周期，与预测horizon是两件事。日线真实链路先交付，周/月若同一日线可派生，必须在本机用candle_periods确定性生成并有边界测试；5m/15m没有权限数据就明确空态，禁止云端兜底采集。

盘中用上一完整session日线做指标/预测时，quote_as_of、bar_end、forecast_as_of分别显示。不能用14:55采集时间把昨日K线/预测包装成盘中实时预测；新鲜quote不能刷新旧forecast资格。日内计算是否变化由输入hash决定，可复用未变结果而新生成完整manifest。

## 4. 展示合同与网站消费（主要实现缺口）

新增独立 `local-display-v2`（live，继承shadow身份与签名存储模式，不直接改v1含义）。manifest至少：contract_version/producer_id、run_id、bundle_id、sequence、generation、code_sha、config_hash、input_snapshot_hash、algorithm_versions、generated_at、每类source_as_of、expires_at/freshness_policy、universe、supported_intervals/horizons、parts hashes、data_origin及资格。来源时间缺失显式null+reason。真实发布端拒绝任何Mock部分，producer也不能自行声明calibrated/actionable。

parts白名单至少覆盖实际正常页面：

| 部分 | 必需字段/行为 |
|---|---|
| overview | 现有compact_row必要quote/returns/indicator/SR/sector/forecast、分页/主题筛选、snapshot identity、digest资格 |
| instrument detail | catalog/name、public quote、指标值与as_of、horizon forecast值/分位/样本/confidence/version/未校准标记、九项availability/缺口和已支持研究投影 |
| charts | OHLCV、raw/research basis、指标与SR/studies、图表周期、成本禁用字段、版本/时点，按generation取 |
| sectors/index summaries | 页面实际使用且已迁移的必要投影；没有许可/数据就explicit unavailable |
| source/status | generation、收发/最后成功时间、freshness per component、兼容性/拒绝原因、producer scope |

逐项盘点Overview.vue/Detail.vue及其子组件实际API调用（news、indexes、Chan、Outlook不能忘）；建立endpoint→part→private-domain→迁移/空态表，不用一个大JSON“自认为完整”。目录搜索可用有界catalog或保留非行情metadataDB；缺标的/周期/新闻不能触发cloud采集。暂未迁移的页面功能应明显unsupported/unavailable，是否构成交付缺项由scope表决定，不能静默读旧云行情混代。

推荐后台compatibility adapter：现有 `/api/workspace/overview`、instruments/{code}详情/图表等URL保持，增加 `WORKSPACE_RESEARCH_SOURCE=database|local_bundle` 与 `local_display_read.py`。同代adapter做过滤/分页/身份白名单映射，不重算指标、研究信号或预测。前端api.ts保持same-origin Cookie登录；加generation pin（响应ID→后续请求generation查询），旧包在请求期间受保护；切换期间出现不存在generation返回明确刷新/冲突，不能详情跨代。

先在认证preview路由验证新adapter，再按配置切正常路径。不要每次页面把旧/新两个结果混合显示。用户收藏/持仓/成本继续来自现有云端私有DB，仅在正常user session且按user_id授权后与公开标的投影合并；不进入上传包、不成为producer下载接口。不为producer授予任何账户读取权限。与行情强耦合的持仓P&L只能使用该generation明示价格/时间，缺quote显示缺口，不fallback旧行情或触发计算。

## 5. HTTPS交付、状态与容量

复用shadow_client/shadow_auth/shadow_bundle实现body hash+active key ID+UTC timestamp+nonce+method/path/scope；新契约使用独立写入scope与独立目录。正常认证user只读，producer只写限定display，不允许配置修改/任意文件/私有GET。服务器小规模展示包校验/hash/分页属于传输展示处理，不是云端研究计算。

接收者必须返回bundle_id、manifest_hash、accepted_sequence、received_at、receiver_version、code/config/contract、status accepted/already_accepted。同一不可变包在响应丢失后使用新nonce重试可返回可核对的already_accepted（不能让原nonce重放成功）；客户端只见HTTP200不算成功，核完整hash/identity后才把outbox标accepted。网络重试上限3次，30秒timeout，退避示例5/15/30秒；超过预算留下失败+最新待传包，下次周期补传未过期最新代，不补传整个陈旧队列。

复用既有etf.joviluma.com HTTPS入口，目标精确path，禁止重定向、HTTP、query凭据/签名URL、关闭TLS校验、新本机入站端口/NAT。网站超限、ENOSPC、perm、bad hash、wrong code/config、future、rollback sequence、过期、nonce重放拒绝后latest保持完整；旧latest/previous语义沿用正式recovery合同，留回滚包；不声称断电事务保证。

状态区分：source新鲜度、transport生成/最后接收、算法资格独立。盘中quote超过15分钟默认stale，其他指标按真实session+source合同判断；包2小时过期沿用fail-closed，不为长期展示悄悄延长有效期。网站可在明确 stale/expired横幅下只读显示最后完成代作历史参考（需要新增专用stale envelope，不是把过期包重新判valid），清掉操作性digest/强弱当前状态；恢复收到新代才切回fresh。周末/盘后无新行情不是采集失败，按日历说明截止session。无任何代明确空态，不能重新拉真实行情。

## 6. 定时计划与重启

时区Asia/Shanghai/可信交易日历。建议两类任务共享锁、输入指纹缓存：

| 触发 | 工作 | 首期边界 |
|---|---|---|
| 初始化/缺历史修复 | 本机历史和catalog种子→暖机/计算 | 有界batch/限速；不重拉全市场 |
| 14:20预热 | 补缺/校验、准备冻结日线 | 不是新实时quote |
| 14:30/14:45/14:50/14:55/15:00/15:15 | 增量quote/必要证据→确定性计算或复用→包→上传 | 单次目标<=120s；不合格记录真实原因/不发假fresh |
| 16:10收盘任务 | 实际可用settled日线增量→下一交易日研究预测→上传 | 未收齐就退避有界；不自己造今日bar |
| 开机/联网恢复 | 最近未过期latest outbox重发；需要时catch-up一次 | coalesce不补跑所有错过slot；全天后台不密集全量拉取 |

Windows正式任务采用现有registrar扩展：绝对Python/代码/数据路径，固定WorkingDirectory，单实例/超时/退出码/轮转日志/上次成功marker。任务身份以Jovi已允许的用户上下文为首选，不创建高权限服务账号；如要注销后运行须选择受支持安全上下文，不能把登录密码放脚本或命令行。首次注册、持久凭据ACL及重启/注销操作需按第10节确认，Agent不擅自重启电脑。任务运行与Codex/浏览器/显卡状态无关。

端到端调度验收至少跨两个交易日实际定时运行，并另测正常启动/睡眠/离线/恢复；7–14交易日长期观察为后续稳定性门槛，不阻挡最小真实链路修复与可回滚部署，不能把等Mock观察当下一步。

## 7. 可借鉴开源及明确取舍

只依赖主仓/官方文档，执行时锁实际commit/version/license/NOTICE，再决定是否复制代码。当前查询不等于已通过所有许可或代码审计。

| 项目/主源 | 可用部分 | 本阶段决定 |
|---|---|---|
| [AKShare](https://github.com/akfamily/akshare) | 财经数据接口库 | 项目已有适配器/依赖，优先复用；软件开源不授予上游行情留存/展示权，另核具体source条款 |
| [DuckDB Parquet](https://duckdb.org/docs/current/data/parquet/overview) | 本机Parquet读写、过滤/列投影 | 借鉴本地分区归档思想；首期不引入双库，实际历史规模超过SQLite预算才单独评估 |
| [Prefect schedules](https://github.com/PrefectHQ/prefect/blob/main/docs/v3/concepts/schedules.mdx) | 调度对象/重试、运行记录思想 | 借有界重试与幂等run_id模式；首期Windows任务+Python足够，不引入控制平面 |
| 既有rotation/AlphaLab/etf-quant评估 | 动量/行业映射/风险研究 | 留在现有OSS评估文档；不为链路打通加入新因子/策略公式 |

可以复用成熟模式：transactional outbox（本机结果先持久化后发送）、不可变content hash、清单指针最后切换、有限retry/jitter、producer/consumer权限分离。采用模式不等于照抄某项目“认证完成/算法可靠”的承诺。

## 8. 执行阶段、文件与回滚

以下所有文件是计划候选范围，不是已修改。每阶段只在干净独立执行分支完成；复用0f8文档基线/f514实施后与最新main审查差异，不能合入另一个未审d013e48分支。原Owner目录保持原状。

### A. 盘点与scope封版

- 文件：AGENTS/STATUS/HANDOFF、workspace/api.py/read_model.py、frontend/src/components/Overview.vue/Detail.vue及子组件、providers/factory.py、scheduler.py；新增docs/audits/LOCAL_LIVE_ENDPOINT_SCOPE.md。
- 只读核当前Git/生产code-image-schema、resource(df/free/受限docker统计)、实际任务清单；不读回显秘密。产出scope表、provider许可/单位/时间缺口、可迁移任务名、cloud表/存储基线。
- PASS条件：全部页面依赖有唯一目标/空态决定；源合法可用；有界部署空间预检明确。无法取得新许可仅停该source，不停止离线开发/测试。
- 回滚：无生产变更。

### B. 本机live采集与确定性计算

- 新增backend/app/workspace/local_compute.py、scripts/run_local_compute.py、非秘密config/local_compute.example.json；保留shadow_export.py的Mock guard，抽取公共projection helpers时保持双路径隔离。
- 现有TaskService/MarketService/ForecastService/ProviderAdapter只做所需profile和审计接入；不改公式。新增backend/tests/test_local_compute.py、test_local_live_provider_boundary.py、test_local_schedule.py。
- 用临时DB迁移测试→可信真实source有界probe→本机owned新DB初始化和版本核对。数据资格与源时间缺口可通过可读研究降级显示但不变actionable。
- 拟新增CLI `python scripts/run_local_compute.py doctor --profile live --root ...`、`... run --once --no-upload`；这是待实现接口，不是当前可用命令。doctor不输出秘密。
- PASS条件：配置完整universe真实nonMock资料本机落库；1/5日等已有forecast真执行或明确warm-up不足；输入/结果哈希可复核；无私有库读取/云写。
- 失败：保留旧本地代，记录failed/partial；不发布半结果。回滚到旧Mock入口不会伪装恢复真实生产。

### C. live-display-v2与网站adapter

- 新增backend/app/workspace/local_display_contract.py/local_display_read.py；更新shadow_projection.py/bundle/auth/client/API支持隔离v2而不改v1含义；core/config.py增加显式source switch。更新workspace/api.py兼容路由与frontend对应metadata/stale/identity展示。
- 新增backend/tests/test_local_display_contract.py、test_local_display_read.py、test_local_delivery_receipt.py；frontend/tests/local-display-consumer.test.ts覆盖正常Overview/Detail/EtfChart，不仅fixture单组件。
- 测试同代分页/详情/图表/forecast、缺失horizon/周期、私有user隔离、signed retry已接受、过期历史参考、无DB原始行情fallback。输出contract/schema、endpoint表、payloadbudget。
- PASS：全UI必需字段与状态在真实投影可消费，producer完全无私有读取。回滚：source开关database，v2receiver关闭；不破坏旧路径。

### D. 精确源码验证与网页复审

- 运行 `python -m pip install -e ".[dev]"` 只在隔离venv必要时执行，market extras按锁定pyproject最小补齐；`pytest -q`、`python -m compileall -q backend/app scripts`、`node --check backend/app/static/app.js`；`npm ci --ignore-scripts --prefix frontend`、前端test/typecheck/build；exact CI+secret scan。
- 必测网络丢回执、timeout/retry、重放/keyrotation/异常时钟、并发+休眠恢复、磁盘满/perm/pointer失败、超预算、过期/Mock漏入live、旧cloud写门禁、持仓认证/CSRF/账号隔离。SQLite本机与生产PostgreSQL行为均验证，不能只看SQLite。
- 交付actual SHA/tree、来源代码/第三方license、脱敏测试矩阵；网页端复审完整diff+收据。所有未跑真实/资源项明确NOT_RUN。
- 禁止调低测试门槛、删原失败、静默启用运行时或提高模型资格。回滚：修复候选，不触生产。

### E. 测试后部署接收端→真实公网preview

- 用现有deploy/compose与受审runbook，若必要新增精准local-display配置。重新确认服务器code/image/schema；部署前容量需覆盖当前运行+回滚镜像、一次新备份、上传/解包临时峰值并留余量。空间不足提出列明清理对象求授权，不能prune全部/删DB备份。
- 新一致性备份/hash、不可变镜像code/tree标签，先部署receiver+认证preview，正常路径仍database，cloud旧计算继续。使用现有HTTPS入口；新producer signing secret由Jovi安全配置，不截图/回显。
- 在本机真实run→网站HTTPS上传→hashreceipt→正常用户浏览preview总览/两只详情图表/forecasts；记录浏览器消费generation/part hash与本机一致。费用/网络无新需求则无需重复授权已允许部署，增加新权限按第10节确认。
- PASS：第9节公网/消费真实证据。失败立即撤回receiver或恢复镜像/配置，不伪装成Mock。

### F. 正常网站切换与云端增长停止

- 通过E后，先正常读开关local_bundle。确认账号/持仓/收藏正常，尚未迁移功能清楚空态；核实际网站消费hash。再精准停止A表列明的cloud采集/指标/forecast/board刷新、手工/admin触发和网页请求侧触发，不停auth维护、备份和必要私有作业。所有入口统一worker_role/display_only guard，不靠只停一个cron。
- scheduler.py、TaskService/API手工任务准入、runtime状态按最小新增role修改；部署保持账户DB可写给私有事务，不能数据库全局只读。不把保留功能持续写行情隐瞒。
- 观察至少一个正常采集周期和两个交易日：已迁移raw market/compute历史表row-count/max-time/bytes无新增，本机相应持续增长；bundle/nonce/log大小有界，API RSS/磁盘斜率有记录。日志/镜像/备份也占盘，另有预算；本项目本轮不清旧资产。
- 失败回滚顺序：先复旧source读配置和旧approved调度角色（有旧数据可用/状态真实），再镜像；不同时运行两个市场计算者造成重复。恢复旧计算是明确审计的回滚，不静默fallback。

### G. 正式调度与交付

- `register_local_compute_task.ps1`或扩展现有registrar；预置绝对路径/profile、非秘密配置、权限、非交互日志、固定源码/配置；脱敏导出任务定义和停止命令。不要替换已有任务同名。
- 在授权任务上下文实际定时跨两个交易日，验证恢复与单实例；禁止Agent自发重启/注销Jovi电脑。交付本机目录、服务/任务名、真实网站generation+截图、开始/停止/回滚命令、source/time/retention门槛、两日实际receipt。
- G完成才标LOCAL_LIVE_TO_WEBSITE_E2E_PASS；若长周期尚未到，标E2E_PASS_WITH_SOAK_PENDING，不冒称7–14交易日完成。算法可靠性仍单独UNKNOWN/not_calibrated。

## 9. 一次性验收表（执行Agent必须填实际结果）

| 条件 | 实证要求 | 当前状态 |
|---|---|---|
| 真实本地源 | source非Mock，许可依据、原始单位/复权/时点/coverage，DB位于本机 | NOT_RUN |
| 本机真实计算 | 同input hash/code/config产生现有指标和forecast；真实不是仅透传fixture | NOT_RUN |
| 本机定时 | Windows实际任务非Codex，至少两个交易日，错过slot/离线恢复可复核 | NOT_RUN |
| 公网签名回执 | 本机→etf.joviluma.com真实HTTPS，received hash==sent hash，失回执幂等可核 | NOT_RUN |
| 正常网站消费 | 正常登录总览/详情/图表/预测已走local_bundle，generation一致，无隐藏cloud计算 | NOT_RUN |
| 离线/过期 | 断本机producer时网站明确stale/缺口，私有功能正常，无假实时摘要 | NOT_RUN |
| Cloud原始增长停 | 所有已迁移入口guard；两个交易日row/byte基线差无新增，展示cache有界 | NOT_RUN |
| 资源减少 | 核实际采集/compute资源下降，磁盘斜率停止；旧数据未删不宣称空间已释放 | NOT_RUN |
| 故障/回滚 | public不影响私有，receiver坏包/掉网/满盘仍完整旧代；镜像+配置可回退 | NOT_RUN |

验收只有原始证据才能PASS；“网页端说方案可行”“CI绿”“fixture PASS”不填以上真实格。真实来源允许展示不等于预测已校准。

## 10. 授权、禁止与阻塞处理

本轮权限定为方案和只读研究，不执行以上业务改动或生产动作。Jovi已表示执行Agent测试后可部署这条链路，后续不重复索要普通实现/测试/既有入口部署授权；执行Agent先核实际可用授权，不因本方案自行扩权。

新收费源/购买/许可接受、新或扩大producer/OS账号权限、秘密生成与安全持久配置、新域名/证书/防火墙/NAT、首次正式常驻任务上下文、新删除旧云历史或镜像/备份范围、电脑重启/注销需要逐项向Jovi说明具体动作后确认。只停被该新条件阻塞的阶段；其他已授权离线代码/测试继续。既有可用HTTPS证书无需为本计划另开网络。

禁止：复制生产DB给本机、原始/私有资料传GitHub/GPT、打印秘密、reset/clean/stash Owner、关闭TLS、开启付费AI、把非实时当实时、用LLM计算/执行数据工具、把未校准标calibrated、自动交易、因为迁移计算就无差别停云服务或删资料。

## 11. 给执行Agent的接手Prompt

按本方案完成真实本地计算→公网网站消费，算法不扩展。先读AGENTS/STATUS/HANDOFF/tasks/lessons，fetch并核main/PR45/其他写入者和生产身份；保护Owner脏文件/配置/数据库。依据固定f514实施及0f8收据，在独立 `codex/local-live-to-website` 执行分支串行完成A–G；没有新增授权不做付费/秘密权限/网络/删除/电脑重启。先写失败测试，保留Mock路径和资格门禁，复用ProviderAdapter/现有算法/HMAC原子store。补live专用入口、完整forecast/detail展示合同和正常网站consumer，然后精确测试、网页GPT复审、备份/受控部署、实际公网验收，最后精确停云端迁移任务并验证行情增长停止。只把脱敏source/test receipts推GitHub。交付actual SHA/tree/image/schema、本机root/任务/停止命令、两个真实交易日记录、网站generation哈希证据、资源前后、PASS/FAIL/NOT_RUN与回滚。不得在Mock/本地TLS阶段宣布链路已完成；遇新授权只暂停相关动作，不停在计划层。

## 12. 双方讨论记录（待复议）

网页端独立提案已实际返回：认可本机计算/网站展示/ProviderAdapter/签名快照/权限域/真实公网consumer验收/Windows任务；建议拆SQLite+DuckDB、举例20GBstore、提出双读及先停cloud计划。

Codex保留项：复用Adapter、独立live guard、scope白名单、公网hash回执、私有域不外泄、freshness与算法资格分开。

Codex待网页复议调整：①首期保持现有SQLite，不为链路建立DuckDB双库；②云store沿用64MiB，20GB示例不适用；③有限K线/报价展示可传，否则网站无法画图，但禁止全历史/provider dump；④先preview/正常consumer切换成功，再精准停cloud所有采集入口；⑤现有预测1/3/5/10日，不能伪造20日/月预测；⑥7–14日soak后续，先做真实公网E2E和两个交易日调度证明；⑦不重复既有部署授权，只问新增权限/采购/删除/重启。
