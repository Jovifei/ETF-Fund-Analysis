# 实现矩阵（发行版 0.6.0）

| 能力 | 实现位置 | 当前证据 | 未完成/部署门槛 |
|---|---|---|---|
| 应用与 Python 包版本 | `backend/app/core/config.py`, `pyproject.toml` | 已设为 `0.6.0`，健康接口/打包元数据可检查 | 发布流水线仍需实际打包验收 |
| ETF/LOF 行情与技术指标 | providers + `indicator_service.py` | 单元/集成测试、Mock 流水线 | Tushare/AKShare 权限、真实字段和实时新鲜度 |
| 策略/信号/回测版本 | `config/strategy.json` | 既有 `signal-v0.4.0` 等策略版本保留；本版未改公式/阈值 | 真实 walk-forward、停牌/涨跌停/LOF 溢价和第二引擎对账 |
| 预测 | `forecast_service.py` | 本地 Mock 生成和测试 | 始终 `not_calibrated`，真实样本外校准与人工封版缺失 |
| 单一主分析 provider | `analysis/`, `analysis_service.py`, config | Codex/OpenAI Responses、Anthropic、DeepSeek 合约和 no-tool 输出测试 | 服务器本地 key/model/base/mode 配置、端点资格；失败不静默切换 |
| 异步 Codex/Claude Code review | review contracts/API | 只读候选与人工 accept 状态已实现 | 仍需人工操作；不能直接写生产或做数值决策 |
| 六项市场上下文 | `market_context/`, `config/market_context.json` | 六卡片、today-change-first、来源/新鲜度渲染与 Mock 测试 | 六项 Provider 真实资格；两项 ETF 代理仍 null/disabled/unverified |
| 新闻 | RSS/Tushare + analysis gateway | 去重、审计和 Mock/heuristic 流程 | 真实新闻权限、稳定 RSS 和模型端点 |
| 持仓截图 OCR | `ocr/`, `holding_import_service.py` | Pillow 校验、私有会话、编辑/拒绝/确认和 no-preconfirm-write 测试 | 真实 Paddle 包、Python 3.12 wheel/model、Linux 私有目录资格；Windows 生产 fail-closed |
| OCR 安全与限制 | `backend/app/core/config.py` + `backend/app/services/holding_import_service.py` | 10MiB 图像、像素/尺寸、60s hard timeout、15m TTL、spawn cleanup | 运维需建立 transient root 0700、模型根私有只读 |
| Docker/反向代理 | `docker-compose.yml`, Dockerfile, Caddy/Nginx examples | Compose/配置可静态检查；代理 body limit 12MB | 当前镜像不装重型 Paddle；缺少显式合格 provision 时 OCR 503；ECS 构建待验证 |
| 数据库迁移 | `backend/alembic/versions` | `158ca7025305` → `9f1c2b3a4d5e` → `a2b3c4d5e6f7` → `b3c4d5e6f7a8` | 真实 PostgreSQL upgrade/downgrade/backup restore |
| 调度器 | `scheduler.py` | 本地 cadence/失败隔离测试；市场上下文默认 15m、tick 30s | ECS 完整交易日观察和告警 |
| 报告/审计 | report/audit services | 本地 HTML/JSON 与输入哈希、来源字段 | 真实数据长期归档和运维恢复演练 |
| 自动交易 | 无 | 明确不实现 | 不得由 Agent 擅自增加 |

## 证据解释

“本地测试”只证明当前代码和合成/Mock 输入；它不升级为真实 Provider、生产 ECS、真实 OCR 或 calibrated 预测证明。任何 Mock、unavailable、未验证代理和缺失核心字段都保持 non-actionable。项目不提供投资建议。
