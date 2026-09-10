# v1.0.4 本地接收、修复与持久部署收据

日期：2026-09-10
性质：本地接收和本地持久部署，**不是生产上线授权**。
远端功能分支：`feat/v104-market-workspace-20260909`
固定接收提交：`910e77fc866f123e0d18103048243513e3edb666`
本轮基线：`57470eabcad35a6038574e893e7245f0d1adb387`
本地审核分支：`codex/v104-news-time-review-20260910`
必要修复提交：`b8112d4`（`fix(v104): align news publication timezone semantics`）

## 1. 接收与保护

固定提交在独立 clone 中接收：

`E:\Claude_allow\Download\ETF-Fund-Analysis-v104-receive-20260910`

验证结果：

- `git merge-base --is-ancestor 57470e... 910e77f...` 退出 0。
- 原工程 `E:\project\ETF-Fund-Analysis` 仍为 `main`、HEAD `11fb295352246769b4f2ae9efaf07d5333bc9c44`，19 个原有暂存路径保持不变。
- 未 reset、clean、stash 原工程；未使用旧 ZIP 覆盖；未强推；未合并 main；未移动标签；未部署服务器。
- 原持久库只读盘点后用 SQLite Backup API 备份；所有真实任务在副本执行。
- 没有读取、回显、提交或截图 `.env`、Token、Cookie、密码、数据库 URI 或个人持仓内容。

接收前数据库副本备份：

`E:\Claude_allow\Download\v104-acceptance-20260910\workspace.sqlite3.pre-v104.sqlite3`

备份时 schema head 为 `d40609090002`，数据库大小 3,940,352 bytes；副本恢复后没有重新 init 既有数据库。

## 2. CI 复核与失败修复

GitHub 网页运行记录显示：

| 工作流 | 运行 | 固定 SHA 结果 | 结论 |
|---|---:|---|---|
| `workspace-ci` | #88 | `910e77f`，Success，2m47s | 工作站合同通过 |
| `public-data-v104-observation` | #1 | `75adfb2`，Success，1m22s | 公开数据观察通过，不代表资格 |
| `ci` | #565 | `910e77f`，Failure，`test` exit 1 | 需要修复 |
| PR `ci` | #566 | `910e77f`，Failure，`test` exit 1 | 与上项同源 |

完整 CI 的失败在本地复现为 `backend/app/static/decision_board_workbuddy.test.js` 仍要求源码包含已经移除的“较昨日”列。v1.0.4 的正确合同是：保留今日涨幅组内排序、其他决策列存在、重复的“较昨日”列不存在。测试已更新为新合同，旧 JS 测试随即 15/15 通过；没有删除测试，也没有放宽认证或数据门禁。远端 CI 没有因本地审核分支而自动重跑，故本收据把“远端原始失败”和“本地修复后通过”分开记录。

## 3. 本地测试结果

独立 Python 3.12.10 环境安装 `.[dev,market]`，前端执行 `npm ci --ignore-scripts`。

| 检查 | 结果 |
|---|---|
| 固定提交初始全量 `pytest -q` | exit 0；5 个条件跳过，未见失败 |
| 修复后全量 `pytest -q` | exit 0；5 个条件跳过，未见失败 |
| 新闻时区专项 | 3 passed：SQLite naive publication、UTC fetched、aware publication 保留 |
| v1.0.4 前端格式专项 | 5/5 passed |
| 旧 WorkBuddy JS | 15/15 passed |
| 旧路由 JS | 4/4 passed |
| `npm run test` | 27/27 passed |
| `npm run typecheck` | exit 0 |
| `npm run build` | exit 0，生成 v1.0.4 workspace_dist |
| `python -m compileall -q backend/app scripts` | exit 0 |
| 7 个旧静态 JS `node --check` | exit 0 |
| committed-secret scan | exit 0，无明显提交密钥 |
| `git diff --check` | exit 0，仅 CRLF 转换提示 |
| clean SQLite `alembic upgrade/head/check` | exit 0，单 head `d40609090002` |
| live 副本 `alembic check` + `PRAGMA integrity_check` | exit 0，`integrity=ok` |
| scoped Ruff | 未作为本轮 CI gate；发现 `workspace/api.py` 7 条既有导入风格问题，未扩大改动范围 |

条件跳过来自 Windows 符号链接/路径权限和未配置专用临时 PostgreSQL。Docker 守护进程不可用，所以 PostgreSQL 容器迁移、生产镜像 build 和容器 smoke 没有被伪称通过。两个 Compose 文件的静态 config 均可解析；根 Compose 使用临时去除私有 `env_file` 的配置验证，未读取私有 env。

## 4. 新闻时间修复

### 4.1 原因

`NewsItem.published_at` 声明了 timezone，但 SQLite 回读后可能是 naive datetime。旧 `news_status.py` 对 publication 和 fetched 都调用 `utc()`，把本应按 `Asia/Shanghai` 解释的发布时间提前/推后 8 小时。前端 `News.vue` 的 `ageHours()` 又直接调用 `Date.parse(String(value))`，没有复用 `stamp()` 对无 offset 字符串的市场时区约定；无效值会变成 `Infinity`。

### 4.2 修复

- `backend/app/workspace/news_status.py` 的 `_market_time()`：有时区的发布时间保持实际时区；SQLite naive 发布时间按 `Settings.timezone` 解释。
- 同文件的 `_utc_time()`：数据库默认 `fetched_at` 的 naive 值按 UTC 解释，并以 UTC 输出；这条路径不影响 publication。
- 未来 publication 不再被压成 0 小时，而是返回 `age_hours=null`、`freshness=unknown`。
- `backend/app/workspace/api.py` 把配置时区注入 news-status read model。
- `frontend/src/lib/format.ts` 增加统一 `relativeAge()` 和共享 timestamp parser；`stamp()`、`olderThan()`、新闻筛选共同使用同一解释。
- `frontend/src/views/News.vue` 对缺失/无效/未来发布时间显示“发布时间待核实”，历史年龄使用有限值，筛选只纳入有效且非未来记录。
- `backend/tests/test_v104_news_status.py` 和 `frontend/tests/format.test.ts` 固化回归；没有批量改写历史数据库。

## 5. 本地持久部署

本地运行副本：

- 数据目录：`E:\Claude_allow\Download\v104-acceptance-20260910\live-data`
- 外部配置：`E:\Claude_allow\Download\v104-acceptance-20260910\workspace-v104.live.env`
- URL：`http://127.0.0.1:8082`
- 运行模式：`APP_ENV=development`、认证开启、`MARKET_PROVIDER=akshare`、Mock fallback 关闭、AI/Bridge/OCR 关闭。
- API 与 worker 由同一 `run_workspace_live.py serve` 启动，共享副本数据库；scheduler 没有由本命令启动。

初次启动 health：HTTP 200，`version=1.0.4`、`provider=akshare`、`auth_enabled=true`。停止自有 API/worker 后用同一配置和数据目录重启，health 再次 HTTP 200。

重启前后只读摘要完全一致：

| 项目 | 重启前 | 重启后 |
|---|---:|---:|
| schema head | `d40609090002` | `d40609090002` |
| ETF 目录 | 1,658 | 1,658 |
| LOF 目录 | 382 | 382 |
| `510300.SH` 日线 | 1,197，2021-10-08 至 2026-09-09 | 同值 |
| `512480.SH` 日线 | 1,197，2021-10-08 至 2026-09-09 | 同值 |
| 行业/概念/全市场板块名数量 | 90 / 614 / 1 | 同值 |
| SQLite integrity | `ok` | `ok` |

这证明缓存和公共数据在本地副本中可持久重启；不证明生产服务器已升级，也不证明真实 Provider 持续稳定。

## 6. 真实目录、板块和有限历史任务

### 6.1 目录/板块同步

管理员测试账号在副本中执行同步，任务终态：

- `catalog=succeeded`：实际目录总数 2,040，其中 ETF 1,658、LOF 382。ETF/LOF 均来自 `akshare:fund_etf_category_sina` 的观察性回退；ETF 曾有 ProviderTimeout、LOF 曾有 ProviderError，故不是“全市场完整”证明。
- `context=partial`：行业快照 partial，插入 176；市场上下文请求 7、收到 6、缺 1、插入 5；指数历史请求 3、成功 2，中证全指 `cn-csi-all` 仍为 `CapabilityUnavailable`。
- 原缓存保留，失败原因显示在任务步骤；没有因为目录同步扩大整个计算池。

### 6.2 两只 ETF 补历史

显式 `onboard` 任务针对 `510300.SH`、`512480.SH`：

- `refresh_bars=partial`：`inserted=1828`、`updated=1`、`unchanged=565`、`instruments=2`、`failures=[]`。
- 两只标的最终各 1,197 根日线，日期 2021-10-08 至 2026-09-09。
- 指标更新 2、展望更新 8；报价刷新为 `TaskExecutionError`，信号和决策板任务仍完成但不提升资格。
- 没有补成交量、没有将 quote 失败伪装成实时成功。

### 6.3 市值/成交额有限准备

只读准备计划返回 `eligible_count=1653`，本次选择 10 只 ETF，少于 30 只上限；按已知市场市值/成交额排序，未知值排后，未推测 AUM。实际准备任务写入 137 根历史，随后指标/展望为 partial、报价为 `TaskExecutionError`，信号/决策板步骤完成。没有自动收藏支付宝场外/联接基金，也没有全目录计算。

### 6.4 指数和新闻重试

- `index_history` 明确重试一次后仍 `requested=3`、成功 2、`cn-csi-all=CapabilityUnavailable`；没有复制点位或 ETF 作为 OHLC。
- `news` 显式任务 `succeeded`，插入 200 条 `akshare:eastmoney`；news-status 返回最新发布时间 `2026-09-10T09:13:23+08:00`、抓取时间 `2026-09-10T01:17:02+00:00`、年龄 0.1 小时、`within_24h`。状态读取本身 `provider_called=false`，符合“GET 不抓取”。
- 2026-09-10 12:58（Asia/Shanghai）再次对两只 ETF 执行 `quotes` 重试，仍为 `partial`：`refresh_quotes=TaskExecutionError`，决策板步骤完成但没有新报价；日线仍以最近已完成交易日为准。
- 生产刷新修复后，本机外部 live env 同步为 `AKSHARE_TIMEOUT_SECONDS=60` 并重启；14:54–14:55 受审计 `refresh_quotes` 对两只 ETF 返回 `inserted=2`、`received=2`、`missing=0`，本机 SQLite 完整性仍为 `ok`。旧 12:58 失败记录保留，不覆盖历史证据。

## 7. 页面与账户验收

真实本地持久副本页面验收使用副本内新建的隔离测试管理员/成员账户，凭据保存在证据目录之外的私有文件，不进入仓库或本收据。验收结果：

- 登录后总览可见，原 WorkBuddy 决策快照仍在唯一市场总览中。
- `元器件` 关联搜索可见，实际返回 62 行；关联原因可见，不把关联说明冒充成持仓穿透。
- ETF 详情日 K、周 K、月 K 均可渲染；`512480.SH` 详情的指标、支撑压力和研究区可读；没有小时数据时仍保留日 K 路径。
- 新闻页 24 小时筛选可用，真实新闻加载后仍没有 `Infinity天前` 或 `0小时前`。
- 因子说明、AI 引导和设置页可见；未发起模型请求。
- 管理员 `/members` 和准备计划返回 200；普通成员访问管理员准备和管理员数据任务返回 403；管理员退出后再访问状态返回 401；没有修改真实持仓。

截图保存在仓库外：

- `E:\Claude_allow\Download\v104-acceptance-20260910\playwright-local-news\local-overview.png`
- `E:\Claude_allow\Download\v104-acceptance-20260910\playwright-local-news\local-detail-month.png`
- `E:\Claude_allow\Download\v104-acceptance-20260910\playwright-local-news\local-news.png`
- `E:\Claude_allow\Download\v104-acceptance-20260910\playwright-local-news\local-settings.png`

自定义本地浏览器验收脚本结果：页面检查通过、`page_error_count=0`、`failed_request_count=0`、坏年龄文本为 false。仓库标准隔离 Playwright 也通过：普通 15/15，认证 2/2。

## 8. AI、OCR、Vibe 与磁盘边界

- 本地持久部署未配置主密钥、API Key 或付费模型；`WORKSPACE_AI_API_ENABLED=false`，保存/浏览没有外呼。仓库单测和隔离认证 E2E 覆盖加密、费用确认、租约、候选审核，但不等于真人模型任务。
- 未复制全局 `auth.json`，未执行 Codex/Vibe 登录、配对或模型调用；Windows DPAPI 真人现场仍待 Jovi 亲自操作。
- OCR 真实图片和 Vibe Windows 上游资格仍未通过；合成/安装/桥接路径不升级资格。
- Docker daemon 不可用，不能据此证明临时 PostgreSQL、生产镜像或容器 smoke；本次只完成 SQLite 副本和直接本地进程部署。
- 只读磁盘/数据库统计限于本地副本；不把本机容器磁盘当成阿里云或用户 E 盘容量。在线 SQLite 不自动云地同步。

## 9. 剩余边界和下一步

本轮已经完成接收、CI 失败修复、新闻时间修复、有限真实源任务、本地持久部署、重启保留和页面验收。仍不能标为完成：

1. 中证全指近期/实时数据仍需 Provider 返回可验证的新时间戳；本次历史入口中该标的失败且旧缓存保留。
2. ETF 成交量、量价因子资格和充分样本的样本外认证。
3. 真实 14:30 point-in-time、5m/15m、费用/滑点/可成交性、purged walk-forward、shadow run。
4. 真实 OCR 图片、Vibe Windows 资格、本人 Codex/Vibe 登录和预算内一次真人研究。
5. API Key 安全凭据的本人主密钥初始化、支付订阅、完整缠论、自动训练和自动云地同步。

下一步应在用户确认后继续：先处理 Provider 资格和数据质量，再做预测校准与事件回测；本地审核分支可继续复核，但不自动合并 main、不自动部署服务器。

## 10. 公网生产部署与刷新修复（2026-09-10）

本节记录本地验收之后的授权生产动作；详细切换、回滚和 hash 见 [`PRODUCTION_DEPLOYMENT_RECEIPT_V104_20260910.md`](PRODUCTION_DEPLOYMENT_RECEIPT_V104_20260910.md)。

- Jovi 明确授权公网生产部署；应用提交为 `3e4b9fa`，`main` 未合并，原工程脏区未触碰。
- 根因是 AKShare 分页现货接口在 20 秒 bounded deadline 内经常超时；配置默认值、示例和生产 Compose 已统一为 60 秒，并新增默认预算回归测试。
- 生产 API、worker、scheduler 使用 `etf-workspace:v1.0.4-runtime-20260910`，公网 health 为 1.0.4；生产 PostgreSQL 备份和旧 v1.0.4 回滚目录保留。
- scheduler `refresh_quotes` 成功：35/35 启用标的写入；`510300.SH`、`512480.SH` 有 2026-09-10 14:30 左右报价，但仍保持 `is_realtime=false`/`public_quote_not_qualified`。
- 受审计两只 ETF 日线补齐至各 1,197 根（2026-09-09）；三只指数缓存各 1,197 根至 2026-09-09。Sina 价格回退的成交量缺失、实时/因子/模型/OCR/Vibe 等未通过资格边界没有改变。
