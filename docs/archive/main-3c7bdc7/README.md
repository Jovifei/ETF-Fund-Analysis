# 中国 ETF / LOF 私有决策看板

一个面向中国场内 ETF/LOF 的个人私有研究系统。它把行情、日线、技术指标、主题新闻、持仓和多期限预测整理成可审计的信号看板，并按北京时间自动刷新。

当前版本：`0.7.0`

> 本项目不连接券商、不自动下单，也不构成投资建议。技术指标、仓位约束和信号状态由确定性程序计算；分析模型只能生成带来源的文本审阅候选，不能计算指标、预测、仓位或交易动作。预测基线保持 `not_calibrated`，在完成真实数据的 walk-forward 验证前，不应作为确定性收益判断。

## 已实现

- 完整档使用 Tushare 主源、AKShare 备用；免费档使用 AKShare 主源，若配置了 Tushare Token 则作为第二候选，生产环境禁止静默回退到 Mock。
- ETF/LOF 自选池、日线、盘中快照、数据源审计和退化标记；技术指标、预测基线、事件驱动轮动回测和信号状态机。
- 新闻去重、主题映射、提示注入隔离和 provider-neutral 多模型分析网关。
- 暗色网页看板、市场上下文卡片、K 线/MACD Canvas 图、持仓录入、SSE 增量更新、HTML 报告。
- 1/3/5/10 交易日终点收益、终点收盘区间、未来路径支撑/压力区和触及频率；未完成前向校准时继续标记 `not_calibrated`。
- 14:30 盘中 quote/OHLCV 仅在隔离的 provisional 研究层更新当前分级、指标解释、图表与支撑压力；1/3/5/10 forecast 在具备同一时点历史盘中样本前始终读取最近已结算日线 `ForecastSnapshot`，页面显示其 `as_of_date`。禁止用当前 14:30 状态直接匹配历史收盘状态冒充盘中预测。
- Alphalens 风格因子 IC/Rank IC/ICIR/分位收益/换手/市场状态诊断，以及可选全局 LightGBM/CatBoost 研究任务。
- XSHG 统一交易日历；实时行情必须拥有可验证的上游时间戳才能成为操作级数据。
- 信号中心研究视图：信号行情曲线（机会/风险/止盈逐日计数）、三张前排推荐、板块强度排名和可调信号系数（0.50–1.50）；命中持仓的条目带账户提醒，仅为研究提示。
- 本地私有 OCR 导入、候选编辑/拒绝/确认流程；确认前不会写入持仓。
- 隔离演示数据模式：420+ 天 Mock 仅写进程内 SQLite，不访问外网或正式数据库；正式行情更新默认回看 120 天。
- 可选 FTShare 只读备用 Provider，默认关闭且未资格验证；需通过有界资格探测后才能进入 AKShare/Tushare fallback 链。
- PostgreSQL、Alembic、FastAPI、独立调度进程、Docker Compose、阿里云 ECS 部署脚本、备份/恢复和 CI。

## 目录

```text
backend/app/               FastAPI、数据层、指标、预测、信号、市场上下文与 OCR
backend/tests/             单元与集成测试
backend/alembic/           数据库迁移
config/                    自选池、策略参数、主题分类、市场上下文注册表
reports/                   运行时报告（默认不入 Git）
deploy/aliyun/             阿里云 ECS 脚本
codex/skills/fund-research Codex 研究 Skill
vendor/                    GitHub 参考仓库清单，不参与运行
```

## 本地 Mock 启动

需要 Python 3.11+；若启用 Paddle OCR，生产资格只接受 Python 3.12/Linux：

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
export APP_ENV=development AUTH_ENABLED=false MARKET_PROVIDER=mock
export DATABASE_URL=sqlite:///./fund_decision.sqlite3
fund-decision bootstrap --lookback-days 420
uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
```

打开 `http://127.0.0.1:8000`。Mock 仅用于验证页面和流水线，所有信号都会被标记为不可执行。

## 私有账户登录

浏览器使用数据库中的闭环账户登录。生产环境显式设置 `AUTH_ENABLED=true`、PostgreSQL
`DATABASE_URL`、`AUTO_CREATE_SCHEMA=false` 与 `AUTH_COOKIE_SECURE=true`，迁移后在服务器本地运行
`fund-decision auth-bootstrap-admin` 创建首个管理员。密码仅以 Argon2id 哈希保存在数据库，会话只在
HttpOnly、SameSite cookie 中存在，浏览器不会把密码或会话写入 localStorage。

生产数据库会话认证不接受 `AUTH_USERNAME`、`AUTH_EMAIL`、`AUTH_PASSWORD_HASH`、`AUTH_SESSION_SECRET` 或旧 Bearer
凭据。本版本没有 SMTP、邮件验证码或 OTP；邮箱登录能力需单独设计和审查。
认证依赖固定为已验证的 `pwdlib[argon2]==0.3.1`、`argon2-cffi==25.1.0` 与 `argon2-cffi-bindings==26.1.0`；更新时必须重新审查密码哈希与登录回归。

## 分析模型配置（单一主 provider）

默认关闭。配置后只启用一个主 provider：Codex/OpenAI Responses。服务器本地 `.env` 使用以下变量：`OPENAI_API_KEY`、`ANALYSIS_PRIMARY_MODEL`、`ANALYSIS_CODEX_BASE_URL`、`ANALYSIS_PRIMARY_MODE=responses`，并设置 `ANALYSIS_ENABLED=true`、`ANALYSIS_CODEX_ENABLED=true`、`ANALYSIS_PRIMARY_PROVIDER=codex_openai_responses`。Anthropic Messages 与 DeepSeek 兼容适配器仅注册为手工切换候选，不能与 Codex 同时启用；失败不会静默切换。

模型无工具、无凭据访问、无数据库/网络抓取/券商能力，也无数值决策权限。Codex/Claude Code 可以在应用生成证据包后异步生成只读审阅候选；只有人工查看并明确接受，候选才可记录为审阅结果。密钥只存在服务器 `.env`，不放入页面、报告、Git 或提示词。

## 市场上下文

默认显示六张卡片，实际观察以 `today_pct_change` 为主、价格为辅。上下文和 ETF 身份均显示来源、时间、新鲜度与 Mock/退化状态。六项定义在 [`config/market_context.json`](config/market_context.json)：

| 卡片 | 默认状态 |
|---|---|
| 中国行业/板块广度与轮动 | 上下文，禁用/未验证 |
| S&P 500 | 指数上下文，禁用/未验证 |
| Nasdaq Composite | 指数上下文，禁用/未验证 |
| Nasdaq-100 | 指数上下文，禁用/未验证 |
| 中国半导体可交易 ETF 代理 | 代理代码为空，禁用/未验证 |
| 韩国半导体可交易 ETF 代理 | 代理代码为空，禁用/未验证 |

代理只有在 Provider 交付交易所代码、日线和现货覆盖、流动性、时间戳与字段质量证明后才可启用。缺失、Mock 或不可用观察均不可产生 actionable 信号；不能用历史快照冒充今日数据。

## 行情数据源与安全演示

看板把数据用途分成三档：隔离演示（Mock）、免费公开行情（AKShare 主源，Tushare 可作为第二候选）和更完整行情（Tushare
主源）。FTShare 是可选的只读备用源，默认 `FTSHARE_ENABLED=false` 且
`FTSHARE_QUALIFICATION=unverified`；应用不会执行第三方 Skill，也不接受前端传入 URL、工具名或
Shell 参数。通过资格探测前，FTShare 完全跳过；探测失败只会记录脱敏状态并继续其他公开源，绝不
静默切换到 Mock。配置项和资格流程见 [`docs/FTSHARE_PROVIDER.md`](docs/FTSHARE_PROVIDER.md)。

系统页的「演示数据」是独立视图：加载后显示 DEMO/Mock 横幅，所有读数仅供研究演示且不可操作；
正式数据和演示数据不会混库。演示状态不会持久化，API 重启后需重新加载。

## 投资组合截图 OCR 操作指南

1. 上传仅限 PNG/JPEG/WebP；Pillow 负责 MIME、魔数、解码、尺寸、像素和尾随数据校验。应用默认最多 10 MiB（`OCR_MAX_IMAGE_BYTES=10485760`）、12,000×12,000、4,000 万像素，硬超时 60 秒，临时会话 TTL 默认 15 分钟。
2. PaddleOCR 是可选本地后端。只有 Python 3.12/Linux 上经过资格验证、私有只读模型目录和严格 `paddle-local-v1` manifest（每个文件含相对路径、字节数、SHA-256，大小有界）才可启用；当前环境没有资格证明，真实 Paddle 包/模型不应被宣称已验证。Docker 镜像不安装重型 Paddle，未显式配置时诚实返回 503/unavailable。
3. `OCR_TRANSIENT_ROOT` 必须是服务器私有、独立的 0700 根目录；模型根目录只读且私有。生产 Windows 直接 fail-closed；生产 Linux 启动时检查目录权限。应用在可杀死的 spawn worker 中运行 OCR，超时会终止并清理，不把原图或原始 OCR 全量写入数据库。
4. 识别结果进入候选表后，操作者必须检查代码/名称、数量、成本、目标权重，编辑或拒绝歧义/重复/低置信度行，再显式确认。任何 OCR 结果都不会自动写持仓；确认后才调用持仓 upsert。云视觉复核默认为关闭，仅在用户明确同意时可用；当前版本不出网、不自动重试、不自动持仓写入。

## 阿里云 ECS 生产部署

详见 [`docs/ALIYUN_DEPLOYMENT.md`](docs/ALIYUN_DEPLOYMENT.md)。核心步骤：

```bash
sudo bash deploy/aliyun/bootstrap_host.sh
sudo mkdir -p /opt/china-fund-decision
cd /opt/china-fund-decision
cp deploy/.env.production.example .env
python3 scripts/generate_secrets.py
# 将生成的值、TUSHARE_TOKEN 和（如需要）分析配置写入 .env
chmod 600 .env
sudo bash deploy/aliyun/deploy.sh
```

Compose 只把应用映射到 `127.0.0.1:8080`，PostgreSQL 不映射宿主机端口。公网访问应经过 Caddy/Nginx HTTPS；ECS 安全组只开放 80/443，SSH 22 仅允许可信 IP。反向代理上传上限应保持 12MB：应用图像上限为 10MiB，额外空间仅用于 multipart 开销；示例已在 Caddy/Nginx 中对齐。

`.env` 用 `chmod 0600`，OCR 临时根目录用 `0700`，模型根目录私有并只读。上线前先备份，并执行 `alembic upgrade head`；随后用 `alembic current` 与 `alembic check` 验证数据库处于仓库当前唯一 head 且没有待生成迁移；回滚只允许在备份和隔离实例验证后使用 `alembic downgrade`，不能直接改生产库。隔离 SQLite 已完成 upgrade/current、完整 downgrade/re-upgrade 和 `alembic check`；该审计修复保留历史 review/analysis hash-check 名称、holding-import opaque-session 约束、nullable legacy calibration JSON 与唯一 `candidate_id` 查询契约。真实 PostgreSQL 的迁移/回滚/备份恢复仍是生产发布门槛。
