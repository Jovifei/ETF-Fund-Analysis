# ETF-Fund-Analysis v105 本地接收与验收收据（2026-09-11）

## 接收身份与保护

- ZIP：`ETF_V105_LOCAL_HANDOFF_20260910.zip`，旁车 SHA-256 与实际文件一致：`a00e87d049f24f9a7993aabaeae50223fec0453ef9cd3f0af1abfce6a9ae07cc`。
- `verify_bundle.py`：`PASS`，713 个文件匹配；工具说明没有打开项目代码或数据库。
- 固定基线：`46c713d4a7f6f247461ec9b075948f25c6741df7`。
- 补丁 SHA-256：`5d86ddf0f8efd68e87915f5eb3fcf3fc3d940391380f182a884392aaa0db2e86`。
- 接收分支：`codex/v105-handoff-local-20260910`，独立 clone；原工程 `E:\project\ETF-Fund-Analysis`、v104 接收 clone、私有配置、账户、持仓和数据库没有作为补丁目标。
- SOURCE_CHANGESET 17 个路径全部匹配。Windows worktree 的 CRLF 与包内 LF 已用换行归一化核对，未修改内容凑 hash。

## 代码与测试提交

包内第一阶段提交：`6e1c0c2 feat(v105): receive stage1 local handoff`。

后续小提交：

- `e072718`：原表指标缺前值时不再显示假“前—变化—”；MACD 跨零用点差，RSI/KDJ 用点数差。
- `9b0822e`：价格级别按 MA/BOLL/ATR/FIB/CHAN/PIVOT 来源筛选，支撑压力与趋势线绘制真实虚线价格 overlay。
- `5a900f7`、`04c4ca4`：AI 方式卡片、步骤面板、复用现有配置；保存不调用模型，旧 button 语义保持兼容。
- `8ba2df7`：全屏关闭显式退出浏览器 fullscreen，Escape 后恢复图表布局。
- `652f2c7`：本地接收任务台账。

现场验证：

- Python 3.12.10：完整 `pytest -q` 无失败；v105 专项 23 项通过。专用 PostgreSQL 条件项未配置，平台条件项按实际跳过。
- Alembic 临时 SQLite：`upgrade head`、`alembic check`、`current` 均通过，head 为 `d40609090002`；未连接用户库。
- Vue：28 项通过、typecheck 通过、生产 build 通过；Node 24.18.0 执行，目标 CI Node 22 未安装，版本偏差已记录。
- 旧 JS：20 项通过；`node --check backend/app/static/app.js`、compileall、密钥扫描、diff check 通过。
- 普通真实 HTTP Playwright：17/17；独立认证 Playwright：2/2。登录后的真实本地 HTTP 页面 page errors=0、失败请求=0、AI 方式切换没有模型 POST。
- 浏览器截图：`E:\Claude_allow\Download\v105-acceptance-20260911\v105-real-overview.png`、`v105-real-detail.png`、`v105-real-news.png`。
- npm audit：报告 3 个漏洞（1 low、2 moderate）；没有执行 `audit fix` 或改变锁文件。

## 本地持久副本与真实数据

原 v104 外部 SQLite 副本先通过 SQLite Backup API 备份到 `E:\Claude_allow\Download\v105-acceptance-20260911\workspace.sqlite3.pre-v105.sqlite3`，再生成 v105 `live-data/workspace.sqlite3`；备份和目标初始 hash 均为 `131d71cafa9c2338f1f9f0c5c89df7dcf425d61911f63de871ab4d46ab5f7c64`，完整性为 `ok`。运行配置仍在仓库外，Mock fallback 关闭，provider 为 AKShare。

本地服务 URL：`http://127.0.0.1:8084`。API、worker 使用同一 v105 源和同一 SQLite 副本；平衡刷新保持 `BALANCED_REFRESH_ENABLED=false`。

真实受审计任务结果：

- 目录：`succeeded`，ETF 1,658、LOF 382，总 2,040；ETF 返回东财 1,605 行，LOF 使用 `fund_etf_category_sina` 回退 382 行，回退原因保留。
- 板块：industry 270、concept 854、market 3，最新日期 2026-09-10，source=akshare。
- 两只 ETF：`510300.SH`、`512480.SH` 各 1,198 根日线，2021-10-08 至 2026-09-10。Sina 回退的成交量按标的分别保留 0/282 个非空行，不填零。
- 现价：两只 ETF 均收到 2 条快照，source=`akshare:em:v101`，`is_realtime=false`，`degraded_reason=public_quote_not_qualified`；源时间、抓取时间分开保留，未冒充实时。
- 指数 OHLC：上证和沪深300缓存各 1,198 根，中证全指缓存 799 根；均为真实 OHLC，不用 ETF 代理或点值复制。中证全指市场上下文仍只有旧源时间 `2016-06-12`，这是当前明确缺口。
- 新闻：本次刷新新增 200 条，副本累计 400 条；`published_at` 与 `fetched_at` 分开处理，未用 `now` 覆盖事件时间。
- 任务链：catalog succeeded；context partial（市场上下文请求 7、收到 6、缺 1；指数历史 3/3）；onboard partial（bars/indicators/forecasts partial，quotes 2/2 但非实时，signals/decision board succeeded）；news succeeded。

## 重启与调度边界

停止 v105 API/worker 后重启同一配置和副本，health 再次返回 v1.0.4/akshare/auth_enabled=true；SQLite integrity 仍为 `ok`，两只 ETF 条数、日期、报价状态不变。数据库文件 hash 从运行前 `ce8a0fa29d3d0ba1018af7188b4d0d93a70de1a1024c65569b11546fa814ac5d` 变为 `d0e1ec23fbb2a528a79d8b2e003e7c5d3a6d89db3b14d582f7ba10d0b4593543`，差异来自 worker 启动心跳等运行元数据，核心数据摘要保持一致。

只启动了一套 scheduler 做现场观察；SQLite 副本在 scheduler 与 worker 同时写任务审计时出现 `database is locked`，已停止该自有 scheduler，保留错误证据。没有把心跳或 HTTP 200 宣称为调度成功，也没有开启 BALANCED_REFRESH_ENABLED。生产 PostgreSQL 不受此本地 SQLite 锁现象影响，本轮不部署服务器。

## 剩余项

1. 专用 PostgreSQL 16 条件测试、Docker 容器和 Node 22 未在本机完成；浏览器普通/认证 HTTP 已在本机真实服务与隔离测试服务分别复测。
2. 中证全指市场上下文近期源时间仍缺失；Sina 成交量缺失；AKShare quote 时间戳仍未完成实时资格；因子、预测和五档动作继续阻断。
3. SQLite scheduler/worker 并发写锁需要单独的架构修复或 PostgreSQL 现场验证；不通过临时静默重试掩盖。
4. Windows DPAPI、真人 Codex/Vibe、付费模型、完整缠论、支付、自动训练、自动云地同步、生产部署均未执行。
