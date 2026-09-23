# Lessons

- 2026-09-23: Windows checkout settings can leave tracked `.sh` files as CRLF in the Git blob; Linux then fails before the script body with `/usr/bin/env: bash\r`. Pin `*.sh text eol=lf` in `.gitattributes` and assert shell entrypoints contain no CR byte; `shellcheck` alone does not catch the shebang failure.

- 2026-09-21: 验收更新必须对账抓取、计算、发布、页面四层；部分失败的历史补抓不得长期占用盘中流水线。数据源选择与业务计算必须使用同一官方企业行为研究视图。

- 2026-09-21: 公共源量额对账要同时使用小数绝对阈值和规模相关相对阈值；只用固定 0.5 元会误拒绝大成交额的正常整数舍入，但相对阈值必须保持在远低于数量级错误的范围。

- 2026-09-21: 当真实响应与文档单位标签冲突时，必须记录冲突并以独立同日对账守住门禁；升级单位合同后不能复用旧 uncertified 证据，必须重算同一绑定行。

- 2026-09-21: Provider 权限受阻时先穷尽仓库已有的公开适配器和真实响应；开源工具可读不等于生产数据认证，必须把适配器合同、实际覆盖、同日独立证据和实时资格分开显示。

- 2026-09-19: 修复任务依赖顺序时必须覆盖所有编排入口，至少同时检查 scheduler 与 `TaskService.full_pipeline`；只验证一个入口会让同类旧顺序继续生成使用过期依赖的决策快照。

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
- 2026-09-11: 原版 WorkBuddy 看板使用的 legacy `/api/decision-board` 不继承 Vue API 的 no-store 约定；数据已落库但浏览器仍可能显示旧快照。凡是可变的 legacy JSON 读路由要同时固定前端 `cache: no-store` 和后端 `Cache-Control: private, no-store`，并用 snapshot_id 做线上回归。
- 2026-09-18: Composite provider 不能把“非空”当作“合格”；低质量 price-only 或 degraded quote 必须继续尝试后备源，并把最后合格历史快照以 stale/非 actionable 方式展示，不能因行业板块成功而提升 ETF 决策资格。
- 2026-09-20: Provider 资格脚本也不能把“三项接口非空”当作 qualified；单位与时间证据必须是显式门禁字段，空字典、字段名和均价比值都不是认证。现场接口恢复后仍需独立同日对账。
