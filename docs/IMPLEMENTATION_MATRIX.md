> **历史基础合同保留**：本文描述旧 main 基础或历史路线；本次 Vue/P0–P4 新增实现、实际测试与未完成项以 [DELIVERY_P0_P4.md](DELIVERY_P0_P4.md) 为准。算法真实性/安全限制继续有效。

# 当前实现矩阵（v0.8.x）

更新时间：2026-09-06  
应用发行版本：`0.8.0`  
导航合同：`v0.8.1`

> “已实现”只表示代码/当前环境具有该能力；“已验证”必须说明验证范围。真实交易有效性、forecast calibrated、真实分钟资格不能由 CI/Mock 代替。

| 能力 | 当前状态 | 已有证据 | 仍缺什么 / 边界 |
|---|---|---|---|
| FastAPI / PostgreSQL / Alembic / SSE | 已实现并有生产运行记录 | v0.8.0 release、迁移 head、容器 health、CI smoke | 每次新部署仍需备份/迁移/smoke；不能沿用旧证据代替新变更验证 |
| 用户认证 / CSRF / 多用户 | 已实现 | HttpOnly Cookie、CSRF、账户/会话/隔离测试 | 生产 secrets 只在服务器；禁止恢复 legacy browser bearer/localStorage |
| ETF 真实日线/spot | 已实现 | AKShare/public composite 实测、生产数据入库 | provider 稳定性需持续 audit；Tushare 为可选增强 |
| 板块行业/概念 | 已实现 | `/boards`、SectorSnapshot、行业/概念数据 | 部分免费概念源缺真实涨跌家数；不得用 ETF 代理伪造 |
| 市场上下文 | 已实现基础 | A股/美股指数、部分 tradable proxy 接入历史 | 韩国半导体代理等仍未完整资格 |
| IndicatorSnapshot 单一权威 | 已完成 v0.8 收敛 | cross-surface tests、请求时重复计算移除 | 指标公式变更需版本升级和验证 |
| canonical current action | 已完成 | DecisionBoard/SignalGrade/Signal fallback 统一、跨页面一致性测试 | 后续 UI/score 不得生成第二套 action |
| Support/Resistance Snapshot | 已完成 | 统一存储、250-bar 口径、跨页面一致性 | 仍需更长期触及率/假突破研究验证 |
| S/R Zone + TD9 价格确认 | 已实现 | zone_low/high、Canvas Zone overlay、TD9 price cluster | 研究算法效果还可长期验证，但不是页面缺失 |
| Forecast 1/3/5/10 | 已实现研究基线 | horizon 对齐、persisted snapshots、purged WFO infrastructure | **仍未 calibrated**；真实 OOS Brier/pinball/coverage 和人工批准未完成 |
| 20D forecast | 非当前运行合同 | 历史 feature 支持/旧 Master Plan | 只有用户重新确认并为 h=20 单独验证后再启用 |
| WorkBuddy 风格 Decision | 已实现并成为首页演进基础 | 五档表、指标解释、来源/时效、统一动作 | UI 仍可优化，但不能恢复前端二次评分 |
| `/boards` 一等板块页 | 已实现 | BoardService + API + static UI | 可继续改善板块长期/多周期强弱，不得改变 breadth 语义 |
| Watchlist | 已实现 | user_watchlist_entries + API + UI | 可继续改善批量管理/独立持仓页体验 |
| Holdings 融合 forecast/action/SR | 已实现 | holdings API + 1/3/5/10 + current action + S/R | 成本线/个人风险在 `/etf/{code}` 的融合还可加强；当前页面仍复用 legacy shell |
| 全局 ETF Detail `/etf/{code}` | 已实现 | 单一详情路由、K线、Zone、指标、forecast、news | 持仓成本线与个人 context 可继续增强 |
| Canvas 交互图表 | 已实现 | wheel zoom / drag pan / reset / crosshair / OHLC / zones | Lightweight Charts 只是历史候选，不是必做迁移 |
| MarketBar 30m/60m 底座 | 已实现 | migration、service、API、detail interval tabs | **真实分钟 Provider 资格未闭环**；缺数据继续 disabled；日K不能冒充分钟 |
| 真实 5m/15m point-in-time | 构建器有，真实数据验证未完成 | `build_1430_point_in_time_dataset.py` / 验证合同 | **最终目标硬阻塞**：真实历史、14:30 cutoff、可成交价、新闻 PIT |
| 14:30 决策模式 | 功能已实现，语义已收敛 | `/decision/1430`、canonical grade、research score、详情跳转 | **历史策略仍 not_qualified**；费用/滑点/事件回测/Shadow Run 未完成；页面仍独立壳 |
| News + provenance layering | 已实现 | heuristic vs model source 明示、实时新闻生产记录 | 模型资格/长期稳定性可继续增强；AI 不能改动作 |
| OCR 持仓截图 | 安全流程已实现 | MIME/像素/候选复核/确认前不写 | 真实 Paddle/model 资格仍受部署环境约束；不是核心 14:30 阻塞 |
| Scheduler | 已实现并增强 miss/resilience | 30s tick、slot/misfire/coalescing、失败隔离 | 继续观察长期交易日运行和 provider 异常 |
| 报告/审计 | 已实现 | provider audit、task、report hash | 长期归档/恢复演练可持续增强 |
| 阿里云生产部署 | v0.8.0 有成功记录 | healthy API/scheduler/db、迁移、同步 | 本轮/未来每次变更仍需独立部署验证 |
| 自动交易 | **明确不实现** | AGENTS 合同 | 不得由 Agent 擅自加入 |

---

## 页面实现状态

| 页面/任务 | 当前路由 | 状态 | 技术债 |
|---|---|---|---|
| 决策 | `/` | 一等页面 | 可继续和 14:30 共用更多组件 |
| 板块 | `/boards` | 一等页面 | 可增强多周期板块趋势 |
| 持仓 | `/holdings` | 一等语义路由 | 底层仍复用 legacy `index.html` + route 激活 |
| 研究 | `/research` | 一等语义路由 | 底层仍复用 legacy shell |
| 新闻 | `/research/news` | 子路由 | 底层仍复用 legacy shell |
| 系统 | `/system` | 工具/管理路由 | 底层仍复用 legacy shell |
| 14:30 | `/decision/1430` | 决策二级模式 | 仍有独立 HTML/JS，尚未真正内嵌 Decision 同一组件树 |
| ETF 详情 | `/etf/{code}` | 全局唯一详情 | 可加入持仓成本线/更强个人 context |

---

## 当前最重要的四个“未完成”

1. **真实 14:30 point-in-time 历史验证**；
2. **1/3/5/10 forecast 真实 OOS 校准**；
3. **真实分钟 Provider / 5m/15m/30m/60m 资格**；
4. **Shadow Run + 人工批准**。

UI legacy 壳拆分属于下一层技术债。不要继续把主要精力用在增加页面/指标数量，而忽略上述证据闭环。

详细步骤见 `ROADMAP_TO_FINAL.md`。
