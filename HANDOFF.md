# 接手入口：v1.0.3

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
