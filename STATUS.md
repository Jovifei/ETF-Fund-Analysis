# 工程状态

更新时间：2026-08-29  
版本：0.6.0

## 已完成并在本地验证

| 模块 | 状态 | 验证范围 |
|---|---|---|
| FastAPI API 与静态看板 | 完成 | TestClient、静态资源、Bearer 鉴权 |
| SQLite 本地/测试模式 | 完成 | 测试和 Mock bootstrap |
| PostgreSQL 数据模型与 Alembic | 完成 | 干净 SQLite 迁移验证；真实 PostgreSQL 待 ECS 验证 |
| Tushare Provider | 已实现 | 代码与权限自适应；用户 Token 尚未实测 |
| AKShare Provider | 已实现 | 代码完成；阿里云出口网络尚未实测 |
| Composite Provider | 完成 | 主备切换、逐源审计、禁止静默 Mock |
| RSS/Atom 新闻 Provider | 完成 | 可选配置；真实 RSS URL 尚未实测 |
| 技术指标 | 完成 | 单元测试、固定口径 |
| 1/5/20 日相似样本预测 | 完成 | 无前视基线与 Mock 数据运行 |
| Walk-forward 预测验证 | 完成 | 生成 JSON；真实数据校准未完成 |
| 事件驱动轮动回测 | 完成研究基线 | 收盘决策、次日开盘、整手、费率、滑点、迟滞、主题分散和风险门控；真实约束待 ECS 数据复核 |
| 信号状态机 | 完成 | 数据门控、组合约束、市场门控、迟滞 |
| 信号中心（读取层研究视图） | 完成 | 信号行情曲线、机会/风险/止盈前排、板块强度、可调系数、持仓命中提醒；`test_signal_center.py` 8 项 |
| 持仓录入 | 完成 | API 与集成测试 |
| 新闻结构化 | 完成 | 启发式 + OpenAI-compatible 客户端；真实模型待实测 |
| HTML 报告 | 完成 | Mock 报告已生成 |
| SSE 增量更新 | 完成 | 使用带 Authorization 的 fetch stream，Token 不放 URL |
| 独立调度器 | 完成 | Mock 环境逻辑验证 |
| 并发任务锁 | 完成 | PostgreSQL advisory lock / 本地进程锁 |
| Docker Compose | 已实现 | 当前执行环境无 Docker，镜像构建待 CI/ECS |
| 阿里云部署脚本 | 已实现 | 待目标 ECS 执行 |
| CI | 完成 | 测试、迁移、JS 检查、Compose 检查、镜像构建 |

## 尚未完成或不能在当前环境诚实验证

1. 你的 Tushare Token 对 `fund_basic`、`fund_daily`、实时 ETF、新闻和交易日历的实际权限。
2. 阿里云 ECS 出口访问 Tushare、AKShare 底层站点和 OpenAI-compatible 端点的稳定性。
3. 真实自选池的基金规模、成交额、费率、跟踪误差、申赎状态和主题纯度数据。
4. 真实分钟线落库；当前盘中技术指标仍以最近已结算日线为基础，实时价格单独进入状态机。
5. 基础事件驱动回测已实现，但真实停牌、涨跌停无法成交、LOF 溢价、现金收益和独立第二引擎对账尚未完成。
6. 预测模型的样本外校准与封版；系统保持 `not_calibrated`。
7. 域名、HTTPS 证书、阿里云安全组、云监控告警和恢复演练。
8. 自动交易。本项目有意不实现。

## 已知设计选择

- 小型个人 ECS 不引入 Redis/Celery，使用 PostgreSQL 任务记录和独立 scheduler，减少运维复杂度。
- SSE 事件存入数据库，API 与 scheduler 跨进程可见。
- 所有报告和信号都保留版本、输入哈希和来源审计。
- 新闻正文是不可信输入；LLM 无工具权限。
- 第三方源码仅供隔离研究，不作为运行时 import 路径。
- 信号中心（v0.6.0 新增）是只读取层：仅消费已落库的 SignalSnapshot/IndicatorSnapshot/新闻/持仓，信号系数只影响该视图的前排分类与曲线口径，不改写生产信号引擎（signal-v0.4.x）的权重、阈值与状态机，因此不触发策略封版与 walk-forward 流程；独立版本号 `signal-center-v0.1.0`。
