# 2026-09-10 本地交接包（V105第一阶段工作稿，尚未发布）

## v105 当前接力（2026-09-11）

v105 已在独立分支 `codex/v105-handoff-local-20260910` 接收并完成本地复测。当前 HEAD 由包第一阶段提交和 R1/R2/R3 小提交组成；生产仍保持 v1.0.4，不自动推送、合并或部署。

本地真实副本运行于 `http://127.0.0.1:8084`，两只 ETF 日线已到 2026-09-10，三指数 OHLC 缓存已记录；中证全指上下文、成交量和实时资格边界保持阻断。SQLite scheduler 与 worker 并发写锁是当前本地部署剩余问题，详见 `docs/LOCAL_ACCEPTANCE_RECEIPT_V105_20260911.md`。

本包基线为 `46c713d4a7f6f247461ec9b075948f25c6741df7`；新增内容用补丁与文件SHA256绑定，没有新的远端应用提交。应用包版本仍为1.0.4。本轮仅源代码及隔离测试，不代表生产发生变化。

先读 `docs/HANDOFF_V105_LOCAL_PACKAGE.md`。待补齐原表重复展示、图表虚线/全屏实测、AI交互、真实数据与Windows部署验收；不能沿用旧报告声明这些通过。平衡刷新默认关闭。以下历史记录原样保留，生产状态必须重新现场核对。

---

# v1.0.4 增量接手

当前功能分支基于main 57470ea，见docs/versions/V1.0.4.md、docs/USER_GUIDE_V104.md和docs/LOCAL_ACCEPTANCE_V104.md。先核对固定SHA与CI，再加载原私有配置/原库副本。不删除以下历史记录，不把分支实现当生产已升级。模型API默认关闭，启用必须初始化独立密钥和本人确认费用。

## 当前公网状态（2026-09-10）

公网 `https://etf.joviluma.com` 已切换到 `3e4b9fa` / v1.0.4。API、worker healthy，scheduler running；生产配置为 `public_composite`、`ALLOW_MOCK_FALLBACK=false`、认证开启。AKShare 分页现货接口的 bounded timeout 已设为 60 秒，scheduler 在 14:35、14:40、14:45 连续成功写入当日两只 ETF 的报价。

生产库备份、旧源目录和回滚 Compose 已保留。两只 ETF 日线目前各 1,197 根至 2026-09-09；三只指数缓存各 1,197 根 OHLC 至 2026-09-09。AKShare 时间戳尚未完成实时资格认证，Sina 回退成交量缺失，因子/预测仍不能晋级 actionable。部署、任务和 hash 证据见 [`docs/PRODUCTION_DEPLOYMENT_RECEIPT_V104_20260910.md`](docs/PRODUCTION_DEPLOYMENT_RECEIPT_V104_20260910.md)。

以下 v1.0.3 段落保留作为历史交接，不覆盖当前 v1.0.4 生产事实。

## v1.0.4 本地接收完成（2026-09-10）

固定接收 `910e77fc866f123e0d18103048243513e3edb666` 已在独立 clone 完成复测。本地审核修复分支为 `codex/v104-news-time-review-20260910`，提交 `b8112d4`，只修复新闻 publication/fetched 时区解释、前端时间筛选/显示和一条过时的 WorkBuddy 列测试合同。

本地持久副本运行于 `http://127.0.0.1:8082`，数据目录在仓库外，使用 SQLite Backup API 从原持久库副本生成；API 和 worker 由同一源版本启动。目录、板块、两只 ETF、10 只有限准备、新闻、页面、账户边界和重启保留均有净化收据，见 `docs/LOCAL_ACCEPTANCE_RECEIPT_V104_20260910.md`。

远端固定 SHA 的 `workspace-ci` 和公开数据观察成功；完整 `ci` 失败原因为旧静态 JS 测试仍要求 v1.0.3 已删除的“较昨日”列，本地已 RED/GREEN 修复，但审核分支未自动推送或触发远端重跑。Docker daemon 不可用，PostgreSQL 容器、生产镜像和服务器部署保持未验证。

不要把本地 8082 当生产站，不要复制隔离测试账号或外部配置，不要在服务器直接 build。AI 主密钥、API Key、Windows DPAPI、Codex/Vibe 登录、真实 OCR、实时/分钟 Provider、中证全指近期数据、量价资格和最终 14:30 研究门禁仍待独立授权和证据。

# 接手入口：v1.0.3

## 最新部署接力（2026-09-09）

当前服务器 commit 为 `c60a15788d5206a407fc6d8a4238137a9ee19b80`，公网 `https://etf.joviluma.com` 的 API/worker 已健康运行。三只指数缓存各 1,196 根；两只 ETF 已重抓到 1,196 根，但 Sina 来源无成交量，因此只允许价格类指标。缺量因子诊断现在返回研究报告并明确 `qualification=not_qualified`，不会改策略。OCR v5 合成图已识别代码/份额/成本；Vibe Windows 上游测试和真人 Codex 任务仍未通过。

部署保留旧镜像回滚 tag和 2026-09-09 PostgreSQL 备份。后续不要在服务器直接 build；当前使用旧运行时镜像加当前 SHA 的只读源码挂载，更新时先备份并保留 staging 目录。

读取AGENTS.md、STATUS.md、docs/README.md、docs/versions/V1.0.3.md和docs/LOCAL_ACCEPTANCE_V103.md。按固定应用提交接收，不从旧main重做或混用旧ZIP。

## 必须保持

原版ETF决策快照嵌在市场总览，不替换成简表或另一主页。左栏/搜索/账户只有一套；原表、目录、详情的收藏使用同一自选服务，退出清空用户状态。

有历史OHLC即允许独立展示，缺实时价格不能让整图空白。历史价格指标与量价/预测/当前动作资格分开。坏标的不阻断其他标的，坏单位不偷偷换算。盘中研究数据有独立时间依据，不能在历史回退时误清。

指数缓存来自真实OHLC适配，不是ETF代理或点值复制；三指数首轮任务会初始化注册表。显式下载任务才取数；GET和recompute/factors不实例化外部SDK。未下载过的目录标的有历史补齐按钮，不制造数据。

## 本地接收任务

保留原工程脏区、外部私有配置、原账户与持久库。在独立worktree/clone，先备份并在副本迁移，再测试。pytest临时库不得连真实数据；后端串行避免共享fixture冲突。

按LOCAL_ACCEPTANCE_V103的L1–L5完成真实ETF与指数下载/重启缓存、原模板/收藏/图表、可选OCR、本人Codex或Vibe单次研究、手动复盘与因子诊断。不能用Mock或者健康心跳冒充真实接通。

API/worker同代码同库，重新构建Vue，不让旧挂载遮住新产物。现有管理员不重置。用户授权范围是本地部署；生产、合并main、改标签必须另行批准。

## 浏览器认证与持久数据库合同

真实部署维持 `AUTH_ENABLED=true`、`DATABASE_URL=<私有持久数据库连接>`、`AUTO_CREATE_SCHEMA=false`。生产HTTPS使用 `AUTH_COOKIE_SECURE=true`；仅本机回环HTTP的live runner允许Secure=false，不得带入生产配置。

数据库由Alembic迁移；确认是空库且尚无管理员时，使用 `fund-decision auth-bootstrap-admin` 交互隐藏输入初始化，不覆盖已有账户。浏览器使用HttpOnly/SameSite Cookie与CSRF，不能把API凭据写入localStorage或恢复旧Bearer登录。生产部署仍需用户另行授权。

## 明确未完成

网站直接API Key安全存储、行情包可信导入/自动双向同步、一个月预测、自动训练/上线参数均未实现。Vibe试部署器和报告导入既有，本轮补引导，尚无本人真实登录/研究产物。q code具体产品未知，不宣称适配。可选环境阻塞记录清楚，不降低门禁。

历史原HANDOFF完整保存在docs/archive/pre-v103/HANDOFF.md；它的生产部署数字和时间仅是当时记录。新验证以docs/VALIDATION_V103.md及固定提交CI为准。
