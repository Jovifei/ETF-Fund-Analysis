# v1.0.1 数据接入与持久部署

## 先分清三个层次

1. 配置/依赖存在：Token 存在、AKShare 包安装、RSS 来源设置，不代表请求成功。
2. 当次读取/入库：目录、日线、现价、分钟、新闻和板块各自观察，失败不伪造/不默默用 Mock。
3. 研究资格：时间可见性、字段单位、校准、可成交性、影子运行仍需独立验证。

以 [v1.0.0 审核](V100_DEPLOYMENT_AUDIT_20260907.md) 为起点，旧的本机 demo 不能承担真实数据接入。

## 已接入能力与不能绕过的条件

| 来源 | 本版代码 | 还需条件 / 保守边界 |
|---|---|---|
| Tushare | fund_basic、fund_daily、rt_etf_k、etf_mins 30/60、新闻候选 | 本人 Token 与每个接口权限；缺少时不调用/不伪装已接通 |
| AKShare | ETF/LOF 目录、东财日线、Sina 日线价格回退、公开现价、新闻、指数与板块 | 网络/限流/接口变化；undated snapshot 不标实时；Sina 量能暂空，仅价格研究，缺量时阻断共享信号 |
| RSS | 配置来源的公开 RSS/Atom，去重和原发布时间 | 必须配置来源；缺时间不填现在；不是新闻搜索引擎 |
| FTShare | 原有适配器保留 | 默认不启用；未 qualified 不入回退链，不绕过服务拒绝 |
| Mock | 独立 demo / 自动化测试 | synthetic；不用于真实投资判断 |

Tushare 官方核对：
- https://tushare.pro/document/2?doc_id=127 ：fund_daily 的 vol=手、amount=千元；本项目转为份额/股数和人民币元。权限以账户及官方当前文档为准。
- https://tushare.pro/document/2?doc_id=400 ：rt_etf_k 沪市 topic=HQ_FND_TICK；trade_time 非默认输出，需 fields 明确请求；该接口的 vol/amount 已为股/元，不再次放大。
- https://tushare.pro/document/2?doc_id=387 ：etf_mins 独立权限，30min/60min；源 bar 时间不等于历史 PIT 可见性证明。
- https://akshare.akfamily.xyz/data/fund/fund_public.html ：不同端点字段/时间语义分开处理。Sina 历史成交量口径仍需交叉验证，不以 README 示例自动取得单位资格。

## Windows 本地真实数据（不是 demo）

在干净的新源码目录；不要覆盖带生产 `.env` 的工作树。Node 只用于构建，正式浏览器由同一个 FastAPI 服务托管。

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[market]"
npm ci --prefix frontend
npm run build --prefix frontend
```

将 `deploy/workspace.live.env.example` 复制到**仓库外**的本人私有目录，手工填 `TUSHARE_TOKEN`（如有）。不要粘贴在聊天、Git、网页普通设置或 shell 参数中。不复制 Codex auth.json，不从 Git 历史找旧凭据。对私有文件设置 Windows ACL；Linux 文件 0600、数据目录 0700。Tushare 优先选择 `MARKET_PROVIDER=composite`，公开源优先为 `public_composite`。

以下路径是需要替换的本机示例，不是本轮已部署的位置：

```powershell
.\.venv\Scripts\python.exe scripts/run_workspace_live.py init --config E:\ETF-Private\workspace.env --data-dir E:\ETF-Private\data
.\.venv\Scripts\python.exe scripts/run_workspace_live.py bootstrap-admin --config E:\ETF-Private\workspace.env --data-dir E:\ETF-Private\data
.\.venv\Scripts\python.exe scripts/run_workspace_live.py serve --config E:\ETF-Private\workspace.env --data-dir E:\ETF-Private\data --port 8082
```

`init` 只允许新数据库，拒绝覆盖；`bootstrap-admin` 隐藏输入密码；`serve` 不自动迁移、不触发首次外网采集，只启动回环 API 和单工作器。关闭时保留数据库。`8081` 临时 demo 与这里 `8082` 不要混淆。
现有数据库升级通过本人离线备份后运行 Alembic（本版 head 未变）；源文件内不要保留与这份本地私有配置冲突的生产 dotenv。

本机 live runner 默认关闭公开注册。若需要在空的本机数据库创建第一个账户，可在仓库外私有 env 中显式设置 `REGISTRATION_ENABLED=true` 和非空 `REGISTRATION_INVITE_CODE`，重启本机 runner 后从 `/classic/etf-board` 的“创建账户”进入；邀请码只用于本机，不要与密码相同。账户创建完成后应移除这两项或改回 `false` 并重启，避免继续开放注册。正式 Docker/生产 Compose 不读取这两个本机 runner 开关，生产账户由管理员流程管理。

浏览器登录后打开“设置 → 后端数据接入”：先检查有效 provider 与依赖，再点“更新跟踪池行情”。首次使用明确配置的 watchlist 作为研究池，无需先抓全市场目录；目录数据不自动让所有 ETF 持续计算。

| 按钮 | 任务 |
|---|---|
| 更新跟踪池行情 | 日线 → 指标 → 预测 → 现价 → 信号 → 唯一快照，核心依赖失败就保留旧快照 |
| 仅更新现价 | 现价与同一决策快照；没有源时间只能研究，不操作 |
| 同步可搜索目录 | 扩展可搜索的 ETF/LOF 目录，不自动启用全市场计算 |
| 初始化选中基金 | 显式开启少量新研究标的，自选/持仓各自保留语义 |
| 同步新闻 / RSS | 独立任务，不依赖所有 ETF 预测成功 |
| 同步指数与板块 | 可选上下文；无法取得时显示缺失，不用 ETF 样本代替全市场 |
| 同步选中基金分钟线 | 先设置 MINUTE_BARS_ENABLED=true，再验证 Tushare 分钟权限；否则明确跳过 |

30/60 分钟图展示不证明 5/15 分钟历史 14:30 回测合格。分钟线不使用日线替代，分钟指标/SR 未统一前保守不可用。

## Docker / PostgreSQL

继续使用 `deploy/compose.workspace.yml` 与仓库外私有 env 文件。默认只启动 api、worker、db；**旧 scheduler 现在属于显式 `scheduled` profile**。不要同时再启动第二个同数据库 scheduler。确实需要原定时方案时先确认资源、回滚和频率，然后显式开启。

```text
docker compose --env-file <private-env> -f deploy/compose.workspace.yml up -d --build db api worker
docker compose --env-file <private-env> -f deploy/compose.workspace.yml exec api fund-decision auth-bootstrap-admin
```

私有 env 需 POSTGRES_PASSWORD，特殊字符 URL 编码/连接字符串口径需自行核实；不要打印 `docker compose config` 到公共日志（它可能展开密钥）。生产使用 TLS/反向代理、Secure Cookie、备份和审计；回环默认配置不是直接公网暴露方案。

## 只读探测与部署证据

```text
python scripts/probe_data_sources_v101.py --public-only --timeout 8 --include-catalog --include-news --output <private-or-review-output>/provider-probe.json
python scripts/audit_workspace_deployment.py --url http://127.0.0.1:8082 --expected-version 1.0.1 --output <review-output>/deployment-audit.json
```

前者只获取有界公共样本；无 `--public-only` 时只读取进程环境中本人明确配置的行情 Token，不搜索旧数据库/文件。返回 probe_complete 仅说明探测结束，实际是否可读看每项 status 与 records；不会写数据库或提升资格。后者不登录，只核对 HTTP 版本、页面、静态资源和 API 404，不代替认证流程/数据库/数据源验收。

## 原 ETF 面板

- `/matrix`：批准的 Vue 壳内的完整五档横向表，MA/MACD/KDJ/TD9/RSI、量能、板块、涨跌、1/3/5/10 历史频率与数据状态。
- `/classic/etf-board`：原 `decision_board_workbuddy.html/js`，源码保留，不是截图。
- 两者同读已有快照；点击 ETF 仍 `/etf/{code}`。指标不是概率；未完成校准不伪称“预测准确率”。

## 故障排查顺序

先看版本与模式（是不是还在 Mock demo）→看依赖与有效 provider→看工作器心跳与任务步骤→看已入库日期/来源→看权限/拒绝/超时→最后才看图表。
Tushare 主链现价失败时直接尝试下一现价源，不对每一只 ETF 串行补日线；日线价格研究与盘中现价是不同任务。Sina 价格回退仍可看 K 线与纯价格指标，但不会用零成交量代替缺量并生成共享新信号。

旧单位提示不能通过“忽略”按钮解除；补全历史重抓后才生成新衍生快照。无权限就保留 unavailable，不绕过付费、数据商或网站限制。

## v1.0.1 生产部署收口（2026-09-07）

生产已完成备份、隔离 staging 恢复与 Alembic、目标镜像切换和 HTTP/HTTPS 验收。运行配置使用 `public_composite`、`ALLOW_MOCK_FALLBACK=false`；API 与单 worker 均 healthy，旧 scheduler 停止，定时复盘、模型、OCR、分钟线仍关闭。生产数据库 head 为 `d40609090002`。

本次远端探测只证明 AKShare Sina 价格日线与新闻可读；两只样本的成交量缺失，目录和公开 quote unavailable。Tushare Token 的存在不等于权限，本次目录、日线、现价和新闻均未通过。由于没有完整量价资格，系统不会用 0 填成交量、Mock 或模型推断来生成新的操作级信号。配置与回滚细节见 [部署收据](DEPLOYMENT_RECEIPT_V101_20260907.md) 和 [生产覆盖文件](../deploy/compose.production.v101.yml)。

## 本版没有接通的能力不是不存在的接口

本版尚未闭环：真实基金净值/IOPV 与溢折价、ETF 穿透持仓、可靠机构持仓变化、5/15 分钟历史 PIT、独立研报全文采集及经校准上涨概率。它们不能由缺失字段、合成数据或模型推断补齐。后续需分别建立数据契约、授权、历史覆盖与验证，不因为 Tushare/AKShare 总体可读就一并标为可用。

如果价格回退只有 Sina 日线，本版允许查看其价格 K 线；缺少量能会阻断新的共享量价信号。后续东财返回完整量能时，会从旧价格历史的最早日期重抓；不会永远卡在增量窗口之外的缺量记录。数据接入状态的“最后已验证源时间”只统计 timestamp_verified 的记录，抓取时间单独显示。
