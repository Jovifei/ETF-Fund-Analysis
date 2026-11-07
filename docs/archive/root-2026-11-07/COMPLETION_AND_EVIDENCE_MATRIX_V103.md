# 完成项、证据与未完成门禁（v1.0.3）

更新时间：2026-09-09  
本文把“已经完成”“部分通过”“明确未通过”分开。数字如果属于不同数据库、不同来源或不同环境，会显式写出环境，不把它们合并成一个看似更大的结果。

## 1. 证据等级

| 等级 | 例子 | 能得出的结论 | 不能得出的结论 |
|---|---|---|---|
| A 源码 | 文件、类型、路由、数据库约束 | 功能路径和安全边界已实现 | 真实源、性能、生产可用 |
| B 隔离测试 | pytest、compileall、Vitest、临时 SQLite、Mock Playwright | 固定输入下行为可复现 | 本人会话、真实 Provider、生产网络 |
| C 真实公共源 | AKShare/Tushare 返回、入库、ProviderAudit | 某次源调用对某些标的有效 | 未来持续稳定、全市场覆盖、可操作 |
| D 生产现场 | API health、worker、HTTPS、备份、重启 | 当前部署进程和部分缓存可用 | 预测正确、模型资格、用户真实任务 |
| E 资格批准 | PIT 数据、样本外、shadow run、人工签字 | 可以升级产品门禁 | 仍不能授权自动交易 |

本版大量工作达到 A–D；P0–P4 的最终 E 级资格仍未完成。

## 2. 已完成能力矩阵

| 能力 | 实现位置 | 当前结论 | 证据边界 |
|---|---|---|---|
| Vue 工作站和统一详情 | `frontend/src/`、`workspace/read_model.py` | 已完成 | 浏览器测试使用隔离夹具；生产真人页面还需用户会话复核 |
| 数据库账户认证 | `auth_service.py`、`core/security.py`、`api/router.py` | 已完成合同 | 不读取/重置用户密码；生产 bootstrap 只允许空库无管理员 |
| ETF/LOF 目录与搜索 | `Instrument`、`Catalog.vue`、搜索 API | 已完成 | 目录可搜不等于已有历史或研究资格 |
| 日线缓存保护 | `MarketService`、批量 upsert | 已完成 | 对已复现的低质量回退覆盖问题有 RED/GREEN 证据 |
| 指数真实 OHLC | `providers/index_history.py`、`workspace/index_history.py` | 已完成三指数入口 | 来源、日期和数量按环境记录；不是 ETF 代理，也不等于实时 |
| 缓存失败/重启保留 | `TaskRun`、`ProviderAudit`、worker | 已完成合同 | 断网复试证明旧缓存 hash 保持；持续 Provider 稳定性仍需运营观察 |
| 指标和支撑/压力 | `indicator_service.py`、`support_resistance_service.py` | 已完成价格类计算 | 缺量、旧单位和未验证分钟线不会越过资格门禁 |
| Forecast 1/3/5/10 | `forecast_service.py`、`pattern_forecast.py` | 已完成研究快照 | 仍 `not_calibrated`，不能宣称上涨概率经过校准 |
| current action 统一读取 | `current_decision_service.py`、`decision_board_service.py` | 已完成语义合同 | `actionable` 仍受实时源、量价和校准状态限制 |
| 因子诊断 | `workspace/factor_diagnostics.py`、`factor_analysis_service.py` | 已完成研究诊断路径 | 缺量时覆盖率为空，整体 `not_qualified`，不改变策略 |
| 持仓导入/OCR 候选 | `holding_import_service.py`、`ocr/*` | 已完成候选/人工确认流程 | 真实用户图片和生产 OCR 模型尚未取得资格 |
| 外部研究包 | `workspace/external_research.py`、Bridge API | 已完成隔离导入与人审 | 没有真人 Codex/Vibe 研究产物，不证明外部模型可用 |
| Docker/ECS 部署 | Compose、Dockerfile、deploy、备份脚本 | 已完成可回滚路径 | 本次服务器采用旧镜像+只读源码挂载，完整重建仍受网络限制 |

## 3. 本地 v1.0.3 接收事实

本地接收使用固定应用提交和外部持久库副本，没有初始化覆盖原账户、持仓和自选。

### 3.1 测试与构建

| 检查 | 结果 | 说明 |
|---|---|---|
| 固定 SHA 全量 pytest | 838 passed，5 条件跳过 | 条件跳过包括 Windows 符号链接权限和专用 PostgreSQL 未配置 |
| 修复后全量 pytest | 845 passed，5 条件跳过 | 串行执行，避免共享 fixture 冲突 |
| v103 专项测试 | 15 passed | 历史、指数、缺量诊断、OCR 等修复合同 |
| Vue 单测/typecheck/build | 24 单测通过 | Node/npm 按前端 engines 安装 |
| Playwright | 普通 12 + 认证 1；真实缓存回放 11/11 | 使用隔离夹具或公开行情包，不是本人生产会话 |
| 旧 JS、compileall、密钥扫描 | 通过 | 不包含原始日志和私有配置 |
| Alembic upgrade/check | 临时空 SQLite 与原库副本通过 | 生产 PostgreSQL 仍需现场维护窗口证据 |

### 3.2 本地真实行情和回放

| 标的/能力 | 本地接收最终事实 | 允许的解释 |
|---|---|---|
| `510300.SH` | 283 根，2025-07-14 至 2026-09-08，`akshare:sina:v101`，缺量 | 历史价格和价格指标可展示；量价/操作资格不提升 |
| `512480.SH` | 282 根完整 `akshare:em:v101` + 1 根新增 Sina 缺量行 | 已有完整行未被低质量回退覆盖 |
| 上证 | 799 根真实 OHLC | 当前收盘日若未收盘必须标记，不当实时 |
| 沪深300 | 799 根真实 OHLC | 四价有真实差异，不是点位复制 |
| 中证全指 | 1,196 根真实 OHLC，腾讯历史端点 | 修复了来源标识字段边界 |
| 实时报价 | 当前同步失败 | 最近收盘仍可读；不能称实时 |
| 归档 | 566 条 ETF/指数缓存，gzip JSONL + SHA256 manifest | 只读归档，不是可信导入或双向同步 |

## 4. 服务器生产事实

服务器当前运行的是审核应用 `c60a15788d5206a407fc6d8a4238137a9ee19b80`，公网域名的 API/worker health 已通过。部署保留 PostgreSQL 备份和旧镜像 rollback tag；生产配置继续关闭 Mock fallback，模型和 OCR 默认关闭。

服务器重试结果：

- 两只 ETF 各 1,196 根日线，至 2026-09-08；Sina 返回缺成交量，因此两者均为价格类可读，量价和 actionable 仍阻断。
- 上证、沪深300、中证全指各 1,196 根 OHLC，来源 `akshare:index:tx-v103`；来源、源日期和失败摘要保留。
- 因子诊断返回 `status=diagnostic`、`instruments=2`、`price_only_instruments=2`、`qualification=not_qualified`、`actionable=false`；`return_20d` 可计算，`volume_ratio` 覆盖率为 0。
- 服务器完整镜像 build 因 `apt-get update` 网络阻塞没有强行替换旧运行时；使用经过测试的只读源挂载，降低回滚风险。

“本地 283 根/799 根”和“服务器 1,196 根”是两个环境的不同收据，不能相加，也不能用服务器较大的数量覆盖本地对固定接收库的验证结论。

## 5. 明确未通过的门禁

### 5.1 数据与因子

成交量缺失导致量价特征覆盖率为 0，因子诊断只能做研究报告。后续要取得合格状态，必须获得同一单位、复权和日期合同下的真实 volume/amount，并按标的、年份、市场状态统计样本；不能补零或从价格推算成交量。

### 5.2 中证全指“近期数据”

端点和来源标识问题已经修复，历史 OHLC 通过；如果用户所说的“近期数据”指的是当前交易日实时或收盘后完整刷新，仍需在真实 Provider 返回新日期、源时间戳和收盘状态后重新验证。历史长度通过不等于当前时点实时资格通过。

### 5.3 OCR

本地合成图适配和超时清理通过，但真实图片没有验收。PaddleOCR v5 的模型布局、manifest 和 PaddleX 输入契约曾不兼容；OCR 仍 fail closed，手工录入可用。任何候选必须人工确认才能落 `Holding`。

### 5.4 Vibe/Codex

Vibe 固定版本的安装器和桥接路径存在，但 Windows 上游测试受符号链接/路径权限影响，状态仍 `not_qualified`。官方 Codex 没有复制全局认证文件，没有自动登录、配对或消耗付费额度；真人任务必须由 Jovi 在自己的会话中完成。

### 5.5 最终研究资格

真实 5m/15m point-in-time 数据、14:30 后可成交价格、费用/滑点/涨跌停/停牌、purged walk-forward、样本外校准和至少 20 个交易日 shadow run 尚未完成。因此 `historical_1430_backtest`、预测 calibrated、自动策略训练和 actionable 仍未通过。

## 6. 回滚与故障处理证据

### 6.1 代码/容器

生产更新顺序是：备份数据库 → 记录旧 commit/镜像 → staging 验证 → 更新 API/worker → health 和数据检查 → 保留 rollback tag。失败时先停止新版本、恢复旧镜像和备份验证；不在生产库直接删除或手工改字段。

### 6.2 Provider

Provider 失败只改变任务状态和 audit，不清空已有缓存。失败摘要使用有限类别，例如 capability unavailable、network、validation、duplicate/conflict；不把第三方 SDK 原始响应直接写进报告。

### 6.3 知识库

Obsidian 写入也有 DryRun、来源 hash、目标 hash、原子写入和冲突停止。工程 Markdown 镜像只从仓库文档根复制，排除 `.env`、tasks、vendor、原始日志和敏感文件。

## 7. 下一阶段验收顺序

```text
真实 14:30 PIT 数据集
  → 5m/15m/30m/60m Provider 资格
  → 1/3/5/10 预测 OOS 校准
  → 事件驱动回测（成本/滑点/可成交性）
  → 20+ 交易日 shadow run
  → 人工批准后才升级资格
```

每个阶段必须同时留下：输入时间边界、来源、版本、样本数量、失败行、指标、hash、人工判断和可回滚动作。不能用一项漂亮结果替代整条链。

