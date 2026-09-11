# Lessons

- 2026-09-07: 接收完整交付包时必须从精确父提交建立隔离分支，并把包内声明与本机重新执行的测试、Provider 可用性和生产服务器盘点分开记录；测试通过不等于真实数据资格或生产切换完成。
- 2026-09-07: Playwright 的失败先区分实现缺陷与测试夹具残留；表格语义用 `scope` 固定，隔离 E2E 数据库每次运行前按受控测试条件清理，避免把上一次状态误判成页面回归。
- 2026-09-07: 登录页显示“创建账户”不代表后端开放注册；必须同时核对 live runner 的数据库用户数、注册开关和邀请码。默认保持关闭，临时本机注册必须显式带邀请码，正式站不可跟随开启。

- 2026-08-30: 当 Jovi 说明本地代码已由其他 Agent 更新时，先重新核对当前主目录的分支、提交、脏区、`STATUS.md`、`HANDOFF.md`、新增测试与运行中服务；不得把旧隔离 worktree 或旧交接摘要当作当前事实源。
- 2026-08-30: 当 Jovi 指出执行过慢时，实施计划必须按任务分层验证：先跑受影响的聚焦测试，任务边界稳定后再跑一次全量；长测试要持续回报进度、检查并发进程和 SQLite 文件锁，不能反复无目的重跑全量。
- 2026-08-31: 决策看板的快照契约必须先逐字段对齐 UI（宽表指标、分组、详情历史/情景/支撑压力、selected horizon）；不能以摘要行替代 snapshot-bound detail，也不能把未验证但完整的免费源 provisional 输入直接丢弃。
- 2026-09-01: 任何看板 snapshot 路由必须支持显式 snapshot_id 复现；回报差值必须说明计算基准；下一刷新与保留策略必须以交易日而不是日历日为边界；替换页面入口时同步调整旧页面兼容测试。
- 2026-09-01: 宽表排序键必须是后端提供的原始数值语义，不能依赖指标对象文本或 UI 猜测；预测排序只可用选定 horizon 的收益和置信度并将缺失值置后。
- 2026-09-01: 排序同档必须提供数值次级键（量比、均线箭头、TD9 计数），并用实际 read/API snapshot payload 验证 horizon 切换，不能只测试纯辅助函数。
- 2026-09-01: Provider percentage-points 与内部 decimal-ratio 必须在边界显式转换一次；任务入队、时效、新鲜度和事件都要以多 session/时间边界测试，而不能只凭单进程顺序假设。
- 2026-09-01: 免费档加入备用 Provider 时，必须同时验证工厂顺序和 RuntimeService/TaskService 对持久化 Token 的实际绑定；只测直接 Settings token 会漏掉 UI 配置无法进入执行链的问题。
- 2026-09-09: Provider audit source labels are bounded data, not free-form endpoint names; keep them under the database field limit or a valid source will be rejected after retrieval.
- 2026-09-09: Shared-signal completeness and research diagnostics are separate gates; allow current-contract price-only data into price-factor diagnostics, but preserve null volume coverage and never promote the result.
- 2026-09-09: PaddleOCR 3.x local models need manifest-listed model names, ndarray input, and Windows oneDNN disabled; keep all decoding inside the bounded child and retain timeout cleanup.
- 2026-09-09: 项目知识库不能只写接力摘要；当项目包含多轮版本、部署、真实源、研究资格和开源借鉴时，必须把产品边界、工程关系、技术路线、完成/未完成证据、可复用经验和 revision/许可证/实际落点分主题记录，并同步到仓库 docs 与 Obsidian 五个核心槽位。
- 2026-09-10: v1.0.4 接收时必须把远端 CI 的当前测试合同与已实现页面合同一起复核；旧 WorkBuddy 测试仍要求已删除的“较昨日”列，不能把 CI 失败归咎于环境，也不能删除该测试。
- 2026-09-10: SQLite 的 DateTime(timezone=True) 回读可能丢失 tz；新闻 publication 的 naive 值按市场时区解释，fetched_at 默认值按 UTC 解释，aware publication 的保留行为要用带时区对象或 PostgreSQL 证据单独测试。
- 2026-09-11: 公开行情回退不能只看 OHLC 是否返回；新浪历史接口同时返回量/额时，必须用 amount÷volume 与 close 的单位一致性回归校验后再解除 volume_missing 门禁，缺额或偏差过大继续保留 price-only，并在生产用受审计 bars→indicators→forecasts→signals→decision-board 链路重算。
