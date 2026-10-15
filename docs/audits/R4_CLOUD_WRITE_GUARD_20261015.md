# R4 云端展示模式研究写入边界

范围：`103522c` 后的一期阻断修复；仅源码与隔离合成验证，不是部署或真实交易日零增长收据。启用条件为 `workspace_research_source=local_bundle`；本机生产者仍使用显式本地 settings 的 database 模式。

## 实施与覆盖矩阵

统一失败类型 `DisplayOnlyTaskRejected` 和 `require_research_write` / `require_task_write` 位于 `services/research_write_guard.py`。父整合负责 HTTP 409 映射；服务拒绝发生在 provider 获取、队列锁或研究 DB 读写之前。

| 入口 | 控制与证据 |
|---|---|
| `TaskService.run` 的所有已知任务 | 原全任务参数化测试保留；默认拒绝，未知任务仍为 UnknownTaskError。覆盖 history/units/quotes/indicators/forecasts/signals/backtest/validation/calibration/model/factor/report 等任务派发。 |
| CLI `run-task` / `bootstrap` / `scheduler-tick` | 前两个在构造 TaskService/provider 和开启业务 Session 前预检；scheduler tick 在 create_provider 前拒绝。 |
| worker `execute` / `run_once` / daily enqueue | execute 返回非零，不加载作业、不绑定 provider；run_once 和日评自动队列不工作；直接历史 execute 无法绕行。 |
| data job enqueue / Chan enqueue / claim | 入队前拒绝；display-only 不 claim 旧队列。catalog/onboard/prepare_history/factors/research_outlook/prices/API 均有负例。 |
| catalog / configured seed / discovery | 所有入口前置 guard；不会更新 Instrument.enabled、目录或 catalog 状态。 |
| factor diagnostics / research outlook / index history | 在读取/计算/获取 provider/写 WorkspacePreference 前拒绝直接调用。 |
| MarketService / MarketContextService 写入口 | 仪器同步、日线、报价、板块、清理旧报价、注册表同步和上下文刷新直接调用也拒绝。 |
| 指标 / 预测 / 信号 / 新闻 / 报告 / 份额 / 分钟服务 | 相应公开刷新/生成写入口前置拒绝；纯读函数不新增抓取或落库。 |
| DecisionBoard queue / refresh / provisional capture | 排队与临时输入均拒绝；refresh 默认拒绝。 |
| SR compute / capture | 直接计算与捕获默认拒绝；latest/latest_or_compute 继续只读，不做 GET 落库。 |
| API 模型 enqueue / execute_ticket | 入队与直调执行前拒绝，不解析私有凭据，不执行付费请求。 |
| 外部研究包 import_packet | 在解析包和写研究证据正文前拒绝；preview 不写。 |
| RuntimeService 设置 GET / 启动默认值 | 默认值在内存合并；local_bundle 的 ensure_defaults 无副作用，不再由 GET/启动补写。 |
| 用户账号 / 已知标的自选 / 持仓 / review / cancel / 私有配置 | 保留用户事务；unknown 自选的 provider 发现路径拒绝。合成持仓/自选增删已验证，未访问真实账户数据。 |

## 受审维护例外

保留原默认关闭的 `display_only_allowed_tasks`。仅精确 `refresh_decision_board` 生效；同配置中的 refresh_bars 无效，`refresh_input=True` 必拒绝。TaskService 成功审计后仅在当前调用作用域允许 board 与必要 SR capture/compute，不能获取报价或记录 provisional input，作用域退出自动撤销。审计事件生成失败时先失败，不进行维护写入。例外会产生明确任务/事件/board/SR 写入；两交易日零增长观察必须将它列为显式例外，不能称零写入。

## RED / GREEN

Python 3.12.10，复用现有隔离 dev 环境，仅合成/mock 和测试库：

- 初始独立入口：23 项，22 FAIL / 1 PASS；`.local/validation-r4/red.xml`。
- 领域直接写入口：36 项，13 FAIL；`red-domain.xml`。
- 外部导入/CLI 新入口：39 项，2 FAIL；`red-final-entry.xml`。
- 维护审计失败：1 FAIL；`red-audit.xml`。
- 最终统一 guard + 原有 TaskService：73 PASS / 0 SKIP / 0 FAIL；`final-guard.xml`。
- worker、目录、outlook、scheduler、自选、外部研究、新闻、报告、上下文、持仓兼容集：264 项，260 PASS / 4 SKIP / 0 FAIL；`final-regression.xml`。该次在最后的维护审计 fail-closed 修正前完成；该最后改动已由上述 73 项覆盖，最终整合全量回归另由父任务记录。
- 选定源文件 compileall 和 git diff --check 通过。

所有 RED 与中间 fixture/环境错误原件保留，没有删除测试或放宽断言。

## 验收边界

本修复是应用入口控制，不是禁止维护人员或任意 Python/SQL 直接连接数据库的数据库角色防火墙。私有认证、账户/持仓、自选与 review/cancel 等用户事务、受审展示包接收存储仍合法。原有 API 读取旧研究数据的展示语义及 generation pin 归 R3，不由此守卫声称完成。

尚未证明：精确发布镜像已生效、云端 DB 角色权限收敛、真实全部 INSERT/UPDATE/bytes 两个交易日计数、受审维护例外在生产中的调用次数、旧队列运维处置、所有 UI 对 409 的操作提示。禁止以 scheduler=false、合成无写 spy 或绿色 CI 替代这些实际证据。旧队列原记录保留，不擅自清理或改状态。
