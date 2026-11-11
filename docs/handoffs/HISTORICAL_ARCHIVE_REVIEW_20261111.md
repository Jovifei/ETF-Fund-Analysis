# 独立历史归档通道：待审候选

## 范围与查重

基线为 `1ec6f38281598d76f6208c96c85704ff9aab8a82`（2026-11-11 只读核对 main）。
PR #53 当前 head 为 `fdaf5426585d64800dbff60656797cd75306f19e`；其核心实现
`f89b3826b637df95e0310a5fdb2a36e21912f9b8` 已是本基线祖先。现有
`LocalDisplayStore` 的 acceptance history 是最多 256 项的实时接收证据，只能恢复曾接受且身份一致的包。
本候选不复制、不放宽这一边界，不修改现有 receiver、reader、outbox、任务台账、实时签名或策略。

当前开放 PR #67 是研究/PIT 回放线，#50 为文档线；已核远端分支没有独立历史归档通道。
本候选与同时进行的外层结构系数回放采用新增文件分工。现有 Muse 集成和生产恢复工作不接管。
仓库 STATUS/HANDOFF 顶部仍有旧 main 状态，不能当作当前运行身份或生产验收依据；此处不覆盖它们。

交付仅为待审代码、合成测试及回滚说明。不部署、不补传、不修改生产权重/规则，不接触用户本地 Agent，
不使用 Cursor 云端，不创建新的 ChatGPT Work/Codex 执行会话。没有读取真实原包、凭据、生产库或实际行情。

## 文件与启用边界

- `backend/app/workspace/historical_archive.py`：独立 SQLite 原字节/回执存储、证据校验、容量与冲突处理。
- `backend/app/workspace/historical_archive_api.py`：独立 FastAPI 工厂与签名辅助函数。
- `backend/tests/test_historical_archive.py`、`test_historical_archive_api.py`：合成回归。
- 本文：接口合同、测试结果、限制及回滚。

`create_archive_app()` 默认关闭，既不创建存储也不注册归档路由。没有模块级 app，没有主站挂载、
CLI/计划任务/Compose/workflow/默认环境配置修改。只有调用方显式提供 `enabled=True`、
`ArchivePolicy` 和专用 `ArchiveCredential` 才会创建独立服务与归档数据库。

新增实际权限、凭据、身份登记、持久卷、入口或部署均须另获批准。本次不生成/保存真实密钥，不读取实时密钥。
上线前必须由实施者完整列出 `protected_roots`（实时展示/sync、outbox、任务状态、研究库、个人事务库等），
使用专用低权限进程及独立持久卷/配额，禁止挂载实时和个人数据卷。路径校验是补充，不是 OS 访问控制替代品。
没有声称本候选已在生产建立这种隔离。

## 原包、时间与证据

仅接收完整原始 `local-display-v2` JSON 字节，传输外壳使用 Base64；不重算、不重写 sequence、manifest 或价格。
原字节 SHA256 单独校验，archive ID 为带 `ETF-HISTORY-ORIGINAL-V1\0` 域的原字节 SHA256。
复用当前 `verify_bundle_integrity()` 的 manifest、parts hash、契约、隐私与 actionable 校验，但不传 `now`，
使过期不被当作完整性失败。根外壳必须恰为 manifest/parts；拒绝重复 JSON key、NaN 和 Infinity。
原始分片必须先由现有受控本机流程完整重组，不能把残缺包、任意研究整库或日志作为原包上传。
本候选没有分片上传或自动重组功能，过大请求直接拒绝，不自动改包。

历史 producer 身份是原 manifest 的 code_sha/config_hash 对；只有显式提供的历史许可集合才算已知。
空集合不会信任任何 producer；未知身份完整原包进入 QUARANTINED，不自动登记、不冒充当前线上身份。
线上消费者/生产者身份本候选不查询，也不由历史身份推断。

证据结构固定为 `history-evidence-v1`：

- original_delivery_status：UNKNOWN / FAILED_DELIVERY / SUPERSEDED / EXPORTED / QUARANTINED / MISSED。
- declared_slot：含时区的原计划时间字符串，无法提供时为 null。原字符串保留，不改时槽。
- market_observed_at：含时区的声明观测时间或 null；不从归档时间合成。
- attempts：最多 100 条，只有 attempted_at、status、error_code、request_id。错误码/请求 ID 为有界字符集，
  不接受自由文本日志、URL、路径、Cookie、Token 或持仓资料。原始证据资料须另行保管，不能塞入上述字段。

本次上传签名只证明当前提交者和请求字节，不证明历史生成/计划/观测时间。
所以 `verified_slot` 始终为 null，`evidence_level=UPLOADER_CLAIM`，迟到秒数明确为
`declared_lateness_seconds`，只按声明时槽计算。生成/过期时间原样记录，到达时过期标记单独计算。
未来生成、未来声明时槽、声明观测晚于生成会隔离而不是篡改原包。
UNKNOWN 的历史 accepted 既不是“未接受过”的证明，也不是已接受证明。

缺原包时只调用 gap 接口记 `GAP_RECORDED`，包 hash/ID 为 null，无行情、无重算。
例如 11-09 原包不存在，不能用今天的数据冒充该时槽。对历史已 DELIVERED 包不能伪造失败状态后走本通道。

## 存储、状态与幂等

原始 bytes、证据及不可变回执在一个 SQLite DELETE-journal/FULL-synchronous 事务中提交。
单库只承载独立归档数据，没有读取或写入主应用数据库。根路径与所有声明保护路径双向不交叠，
拒绝符号链接/硬链接及未知目录项。首次创建目录 mode 0700，数据库 mode 0600，不改已有目录权限。
该检查不是对本机恶意特权用户的安全隔离承诺。

- 相同原字节、相同证据返回首份相同回执（包括 ID/首次归档时间），重启/回执丢失后可查。
- 相同原字节、不同证据返回 409 evidence conflict，不静默覆盖第一次记录。
- 同 producer/config/sequence 的不同原字节，后来的记录 QUARANTINED，并列明冲突 ID。
  即使只是 JSON 空白差异，也按不同原字节处理。首份回执不回写；新冲突不能让历史数据成为实时可用数据。
- 未知身份及矛盾时间证据保留完整且契约合格的原字节，进入 QUARANTINED。
- Hash、契约、隐私、完整性不合格的输入 REJECTED，只存摘要回执，不留拒绝原文。
  拒绝事件使用不同 ID 域，不会抢占正确原包的 archive ID。
- 查询不到返回 `status=UNKNOWN, realtime_acceptance=UNKNOWN`，不返回 not_accepted 或可重传实时的结论。
- 不可变归档回执采用 `historical-archive-receipt-v1`，状态不等于实时 accepted/DELIVERED。
  原 FAILED_DELIVERY / SUPERSEDED 原样保留；不回写原 ledger，不发邮件，不触发交易/决策。

默认候选上限：总目录 128 MiB、原包 8 MiB、证据 32 KiB、同时一写一读、正文读取总时限 10 秒、
至少保留 1 GiB 文件系统空闲、最多 3000 个有效写 nonce。它们只是待审参数，不是生产已配置数值。
原包上限可显式提高但不可超过当前契约 64 MiB。容量检查保守预留整库回滚 journal、原包增长和索引空间，
另有 SQLite page 上限与提交前检查。无法保留资源就停止写入；没有自动删除原包、回执、冲突、gap 或实时数据。
没有自动保留期、压缩、驱逐或清理任务。持久留存与备份容量须上线前另定。

## 独立 HTTP 合同

前缀 `/api/history-archive`，仅独立 app 内存在：

1. `POST /objects`，外壳恰为 `{contract: historical-archive-submit-v1, original_sha256, original_base64, evidence}`。
   ARCHIVED=200，QUARANTINED=202，REJECTED=422，响应为上述独立回执。
2. `POST /gaps`，外壳恰为 `{contract: historical-archive-gap-v1, reason, evidence}`。
   reason 为 original_missing / original_unreadable / evidence_missing，成功返回 GAP_RECORDED=200。
3. `GET /receipts/{archive_id}`，只读查询回执，未知为 HTTP 200 / UNKNOWN。
4. `GET /objects/{archive_id}`，专用读权限回读精确原字节并重新验 SHA；不存在/拒绝/gap 无原字节时 404。

只认 `X-Archive-Key-Id/Timestamp/Nonce/Signature`。签名域为独立
`ETF-HISTORICAL-ARCHIVE-REQUEST-V1\0ARCHIVE_ONLY\0`，绑定 HTTP 方法、精确路径、key ID、UTC 秒时间、
nonce 和请求 body hash。实时 Shadow 签名即使改 header 名也无效。key 不从现有 settings/env 继承。
`archive:submit` 与 `archive:read` 分开授予，默认没有权限；可以明确授同一专用身份两种 scope，不能自动沿用实时角色。

签名在开始及读取正文完成后都校验 ±120 秒，回执/nonce 用完成时钟。
POST nonce 耐久存储，重放 409，读超时 408，限流/容量/存储不可用 503，过大 413。
读取采用独立并发槽，慢上传不能占尽回执查询。GET 无副作用，在签名有效时窗内允许只读重放；
使用 SQLite mode=ro，不预留 nonce，使写满后仍可查询旧回执。所有响应 no-store。
超时或连接不确定：客户端先按本地原字节计算的 archive ID 查询，UNKNOWN 只允许决定是否用新 nonce
重试同一归档请求，不允许假定实时从未接受、改 sequence 或重算。

## 已实际执行的验证

Python 3.12 隔离 venv，按当前 `.[dev]` 声明安装，没有修改依赖文件/锁文件。未使用真实行情和生产端点。

- 初始测试先行：存储/API 模块不存在时分别得到 collection error；不冒充 47 项行为全红。
- 满盘回执查询回归：初版 503 失败，改为只读 GET 后通过。
- 独立复审实证慢 body 可越过签名时间窗；两个新增回归均先失败，读取总超时与完成时复验后通过。
- 新增归档专项 **47 passed / 0 failed / 0 skipped**。
- 新增归档 + 原有 receiver/consumer/generation/cache/auth/chunk/API/job ledger 组合 **157 passed / 0 failed / 0 skipped**。
- 已覆盖：原字节回读、首次身份、不伪造时槽、expired、未知 producer、同序异包、重复并发、拒绝隐私/篡改/
  重复 key/非有限数、独立读写权限、实时签名域拒绝、耐久 nonce、回执丢失查询、原 ledger/live 指针不变、
  旧未接受实时包仍拒绝、低磁盘/总配额、真实子进程 `os._exit(93)` 事务中断及恢复。
- Ruff 新增四文件、Python compileall、静态 app.js 语法检查：通过。
- 全量后端 pytest 由组合候选另行执行，结果以对应组合收据为准，不能由 157 项替代。

未验证：真实 Windows/生产部署、跨物理磁盘 I/O 故障、主机资源争抢、真实原包容量/时效、身份登记或历史可信时槽证明，
公网 TLS/反向代理/凭据轮换/备份恢复及真实补档。该候选没有这些操作的授权，不宣称已可上线。
当前合成测试中原有 SQLAlchemy registry 警告和 Starlette/httpx 弃用警告仍保留。

## 回滚与接收顺序

本次仅新增独立文件，未挂主站，因此未合入时直接不接收补丁即可，线上无需任何回滚动作。
如将来单独获准合入：停止独立入口/撤销其专用凭据，取消独立服务进程的启动，不动实时接口或策略。
先停止归档写入、保全专用数据库及可能存在的 rollback journal，再通过 SQLite 正常恢复/备份流程检查
`PRAGMA integrity_check`，抽样按回执 hash 回读原包；不得盲删 journal、归档原包、gap、失败证据或线上数据。
禁止用生产库覆盖归档库，禁止把归档库恢复为 live latest/previous。

接收时固定最终代码 SHA 与测试收据，重新核 main/实施者避免重叠，再复验本测试集及必要组合全量。
没有启用许可时保持默认关闭；后续部署、历史身份许可集合、凭据/权限/独立卷以及实际原包补传须分别按批准范围执行。
归档成功只证明本候选收到并校验了特定字节，不证明准时交付、行情真实、策略有效或任何资格晋升。
