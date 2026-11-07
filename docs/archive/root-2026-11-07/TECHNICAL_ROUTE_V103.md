# 技术路线与工程关系（v1.0.3）

更新时间：2026-09-09  
本文回答三个问题：请求和任务怎样穿过系统、每个模块为什么存在、下一阶段应沿哪条技术路线继续。它以当前代码为准，历史设计和未来候选会明确标注。

## 1. 总体设计原则

### 1.1 确定性核心，模型只做解释

价格、收益、MA、MACD、KDJ、RSI、TD9、支撑/压力、样本计数、资格状态和五档 current action 都由 Python 服务和持久化快照产生。模型不计算这些数值，不读取数据库，不执行 Shell，不抓取网络，也不写持仓或信号。

模型可以做的事情是：在已冻结、带来源和 hash 的证据包上生成事实、推断、风险和冲突文字；结果进入 `AgentReviewCandidate` 或外部研究包，必须人工查看才能成为审阅记录。

### 1.2 所有外部数据先经过 Adapter

业务代码不写 AKShare/Tushare/网页私有接口。调用链是：

```text
任务请求
  → TaskService / Workspace protocol
  → MarketProvider 工厂
  → composite 主备策略
  → 具体 Adapter
  → BarRecord / QuoteRecord / NewsRecord
  → 字段、时间、单位、质量和来源校验
  → 批次保存 + ProviderAudit
```

这样做的意义是把“某个源今天返回了什么”与“系统如何使用标准记录”分开。新增源时只扩展 Adapter 和能力声明，不在服务和前端散落站点字段。

### 1.3 页面读取缓存，显式任务才取数

页面 GET 只能读已有数据库快照。刷新页面不会自动拉行情、跑模型、重算回测或修改自选。用户点击下载、补齐历史、刷新指数、因子诊断、分钟线或外部研究时，才创建有界任务；worker 领取任务、执行、写入状态并释放租约。

## 2. 请求路径：从浏览器到数据库

### 2.1 登录与会话

```text
Vue Login.vue
  → /api/auth/login
  → auth_service 校验数据库账户/Argon2id
  → HttpOnly + SameSite + Secure Cookie
  → /api/auth/me / private_router
  → user_id 注入各工作站服务
```

生产不使用 `AUTH_USERNAME`、`AUTH_EMAIL`、预置 hash、旧 Bearer token 或浏览器 localStorage 代替数据库认证。首次管理员只能在确认数据库为空且没有管理员时，通过交互式 bootstrap 建立；现有账户不重置、不覆盖。

### 2.2 总览与详情

```text
Overview.vue / Detail.vue
  → frontend/lib/api.ts
  → /api/workspace/* 或旧兼容 API
  → workspace/read_model.py / DashboardService
  → DailyBar、QuoteSnapshot、IndicatorSnapshot、ForecastSnapshot、
    SupportResistanceSnapshot、SignalSnapshot、DecisionBoardSnapshot
  → 统一 JSON payload
```

总览和详情不各自计算一套指标。`IndicatorSnapshot`、`SupportResistanceSnapshot` 和 canonical current action 是跨页面的权威来源；页面只负责格式化、排序、交互和风险提示。

### 2.3 搜索和统一详情入口

`Catalog.vue` 使用 `/api/search/instruments` 搜索全目录，搜索不代表该标的已有历史。点击代码或名称统一进入 `/etf/{code}`；`routerFactory.ts` 把旧 `/workbench/kline`、`/legacy`、`/matrix` 和旧 14:30 入口重定向到新路径，保留书签兼容。

## 3. 行情数据路径

### 3.1 ETF/LOF 日线

```text
refresh / onboard / prices 任务
  → TaskService
  → MarketService.refresh_daily_bars
  → Provider.fetch_daily_bars
  → normalize BarRecord
  → duplicate / quality / unit / date checks
  → savepoint + 批量 upsert
  → ProviderAudit + TaskRun
  → DailyBar
```

v1.0.3 修复前，Sina 价格回退可能覆盖同日期完整缓存；修复后按标的批量读取现有行，在同日比较质量，完整来源优先，缺量行只能作为 price-only 新数据。网络失败不删除旧缓存，也不把部分成功改写成全量成功。

### 3.2 指数 OHLC

指数走独立的 `providers/index_history.py` 和 `workspace/index_history.py`，当前支持：

| 业务名称 | 代码 | 允许的真实数据 |
|---|---|---|
| 上证综合 | `sh000001` / `cn-shanghai-composite` | open/high/low/close，真实指数 OHLC |
| 沪深 300 | `sh000300` / `cn-csi300` | open/high/low/close，真实指数 OHLC |
| 中证全指 | `sh000985` / `cn-csi-all` | open/high/low/close，真实指数 OHLC |

禁止把 ETF 收盘价复制成指数四价，也禁止把只有点位的观察结果冒充蜡烛图。指数缓存保存源标识、源日期、逐行 hash 和批次摘要；整批校验后合并，失败保留旧缓存。

### 3.3 实时报价和分钟线

报价、分钟线和历史收盘是三条不同路径。没有可靠的 source timestamp 时，页面可以显示最近历史收盘，但必须标出 `historical_close`；没有真实 5m/15m 数据时，30m/60m tab 禁用，不能从 1d 下采样伪造。`MarketBarService` 将分钟资格保持为 `historical_pit_not_verified`，因此它不进入 14:30 可操作门禁。

## 4. 计算路径

### 4.1 指标

`IndicatorService` 和 `utils/indicators.py` 负责确定性指标；`utils/indicators_v05.py` 和 `structure_indicators.py` 扩展收益、量比、VWAP、OBV、MFI、CMF、RSRS 等研究特征。服务从已存历史计算，缺历史或缺量时返回缺失状态，不从前端或模型补值。指标版本写入快照，改变公式或初始化必须升级版本并重新验证。

### 4.2 支撑/压力

`SupportResistanceService` 统一生成 `zone_low`、`zone_high`、`strength`、`methods`。K 线详情和 14:30 模式读取同一快照；振荡器不能直接当价格；最新报价与已确认日线快照不同步时，页面必须显示提示。

### 4.3 Forecast

`ForecastService` 保存 1/3/5/10 交易日快照，`pattern_forecast.py` 的历史相似样本结果默认 `calibration_status=not_calibrated`。`PreflightService` 检查是否有足够历史、时间边界、来源、样本数量和校准状态；未完成 purged walk-forward、Holdout、泄漏检查和人工批准前，不能改成 `calibrated`。

### 4.4 Signal 和 current action

`SignalService`、`SignalGradeService`、`CurrentDecisionService` 和 `DecisionBoardService` 共享 current action 语义。解释分数、Signal Center 排名和 14:30 component score 不能各自生成第二个动作；页面最终只读取 canonical 五档：可加仓、可入场、可试探、观望、减仓。

## 5. 异步任务路径

### 5.1 任务合同

`workspace/protocol.py` 定义任务类型、代码列表、因子列表、horizon、版本和结果结构。当前任务类别包括 refresh、onboard、factors、validate、shadow_audit、prices、quotes、catalog、news、context、minutes、index_history、recompute。

任务请求必须满足：

- 代码格式、因子名称和任务类型白名单；
- 同一用户/目标的幂等键；
- 有界代码数、因子数、输出大小和超时；
- 失败分类只保存安全摘要，不把第三方异常原文写入报告；
- 任务结果写明 `succeeded`、`partial`、`failed` 或 `skipped`，不隐藏部分失败。

### 5.2 worker 和 scheduler

`workspace/worker.py` 是显式任务 worker；`scheduler.py` 是可选调度进程。两者使用同一个应用源、数据库和配置合同。worker 通过 lease 防止重复领取，过期 lease 会变成失败；重试必须满足任务状态和预算限制。生产首启可关闭 scheduler，待 Provider、数据库和备份验收后再启用。

### 5.3 缓存重启合同

缓存重启验收不是“服务进程又启动了”，而是：

1. 重启前记录条数、日期范围、来源和 hash。
2. 让外部源不可达，重新尝试任务。
3. 任务明确失败或 partial，旧数据不被清空。
4. 重启 API/worker 后再次读取，条数、日期、hash 和价格指标保持不变。
5. 恢复网络后允许显式重试，成功结果有新 ProviderAudit。

## 6. 因子、模型和外部研究路径

### 6.1 缺量因子诊断

因子页允许用户从注册表选择因子，后台复用现有确定性特征构造 pairwise panel，计算样本数、Spearman、Rank IC、ICIR、分组收益和换手等诊断。缺成交量时，`volume_ratio`、`amount_ratio` 等字段保持空覆盖率；价格因子可以返回研究结果，但整体 `qualification=not_qualified`、`actionable=false`，不会调整策略权重。

### 6.2 外部研究 Bridge

```text
站内创建冻结证据包
  → 本地 Codex/Vibe 客户端主动领取
  → 设备配对码 + lease + 预算
  → 外部客户端一次性生成结果
  → schema/hash/输入匹配检查
  → 站内预览
  → 人工接受或拒绝
```

Bridge 不把网站连接到用户电脑 localhost，也不上传全局 `auth.json`。外部导入只允许有限原生文件，剔除认证目录；hash 只证明文件未被改动，不证明作者、模型身份或结论正确。

### 6.3 OCR 持仓导入

```text
PNG/JPEG/WebP
  → MIME / magic / decode / 尺寸 / 像素 / 字节校验
  → 私有临时目录
  → 可选 PaddleOCR 子进程（硬超时、可清理）
  → code/name/shares/cost/target_weight 候选
  → 用户编辑、消歧、拒绝
  → 明确确认
  → HoldingService.upsert
```

应用不保存原图和完整原始 OCR payload；真实 OCR 失败时仍允许手工导入。OCR 识别候选不是持仓事实，只有用户确认才写库。

## 7. 存储、迁移和部署关系

### 7.1 本地测试

- Python 3.11+，正式 OCR/生产路径按 Python 3.12/Linux 资格检查。
- SQLite 用于隔离单测、离线回放和临时迁移；不能拿它证明生产 PostgreSQL 行为。
- `alembic upgrade head`、`alembic check` 和 integrity 检查必须在隔离库运行。

### 7.2 生产 Compose

`docker-compose.yml` 启动 `db`、`api` 和可选 `scheduler`：

- PostgreSQL 16 数据卷不映射公网端口；
- API 只绑定宿主机回环 8080；公网通过 Caddy/Nginx HTTPS；
- API/scheduler 使用只读源码和配置挂载、非 root 用户、`no-new-privileges`、cap drop 和 tmpfs OCR 临时目录；
- API 启动前执行 Alembic，healthcheck 只证明进程和数据库可用；
- reports/backups 是受控写目录，不存 `.env` 或密钥。

### 7.3 本次服务器部署

服务器使用旧已审计运行时镜像作为基底，挂载经过测试的 `c60a157` 只读源码和 Vue 产物；保留旧镜像 rollback tag 和 PostgreSQL 备份。API、worker 和公网 health 已现场验证。远端完整重建因 apt 网络阻塞没有强行采用，避免在资源受限服务器上留下半成品。

## 8. 技术债与演进顺序

当前仍保留的结构性技术债：

- `/holdings`、`/research`、`/system` 部分入口仍复用 legacy shell；
- 静态旧 HTML/JS 仍作为回滚和兼容资产；
- 真实分钟 Provider、14:30 PIT 数据和费用/滑点约束还没有完整资格；
- 数据归档已经能导出 gzip JSONL + manifest，但没有可信签名导入和自动双向同步；
- API Key 安全凭据存储尚未开放；
- 大模型、LightGBM、Riskfolio、第二回测引擎均是隔离研究候选，不能自动晋升生产。

正确的演进顺序是先补 P0/P1 的真实时间序列和数据资格，再做 P2 预测校准、P3 事件回测、P4 shadow run；页面拆分和视觉增强只在不改变数据合同的情况下并行。

## 9. 代码阅读导航

| 目标 | 首读文件 |
|---|---|
| 应用启动与路由 | `backend/app/main.py`、`backend/app/api/router.py` |
| 配置和版本 | `backend/app/core/config.py`、`config/strategy.json`、`pyproject.toml` |
| 数据实体 | `backend/app/models/entities.py`、`backend/app/workspace/models.py` |
| 外部行情 | `backend/app/providers/base.py`、`composite.py`、`akshare.py`、`tushare.py`、`index_history.py` |
| 任务与 worker | `backend/app/workspace/protocol.py`、`data_jobs.py`、`worker.py`、`backend/app/scheduler.py` |
| 指标和信号 | `backend/app/services/indicator_service.py`、`forecast_service.py`、`signal_service.py`、`current_decision_service.py` |
| OCR 与持仓 | `backend/app/ocr/*`、`backend/app/services/holding_import_service.py`、`holding_service.py` |
| 外部研究 | `backend/app/workspace/external_research.py`、`bridge_api.py`、`review_service.py` |
| Vue 入口 | `frontend/src/App.vue`、`routerFactory.ts`、`views/`、`components/` |
| 部署 | `docker-compose.yml`、`backend/Dockerfile`、`deploy/`、`docs/ALIYUN_DEPLOYMENT.md` |

