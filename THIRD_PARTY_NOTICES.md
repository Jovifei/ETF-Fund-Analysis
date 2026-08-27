# Third-party notices

本项目自身代码使用 MIT License。运行时 Python 包和容器镜像各自受其许可证约束，请以实际安装版本随附的许可证为准。

## 直接运行依赖

| 组件 | 用途 | 常见许可证 |
|---|---|---|
| FastAPI / Starlette | API 与 SSE | MIT / BSD-3-Clause |
| Uvicorn | ASGI Server | BSD-3-Clause |
| SQLAlchemy / Alembic | ORM 与迁移 | MIT |
| Pydantic / pydantic-settings | 配置和 Schema | MIT |
| Pandas / NumPy | 数据处理 | BSD-3-Clause |
| HTTPX | 外部 API | BSD-3-Clause |
| Jinja2 | HTML 报告 | BSD-3-Clause |
| Typer | CLI | MIT |
| psycopg | PostgreSQL | LGPL-3.0 with exceptions |
| Tushare SDK | 中国市场数据接口 | 以其软件和服务条款为准 |
| AKShare | 备用财经数据适配 | MIT |
| feedparser | RSS/Atom 解析 | BSD-2-Clause |
| PostgreSQL | 数据库 | PostgreSQL License |

## GitHub 设计参考

本项目基于公开资料重新实现或适配以下设计思想，没有把它们设为生产运行时 import 依赖：

| 仓库 | 许可证/限制 | 使用方式 |
|---|---|---|
| thincat75/fund-rotation-analyst | MIT | 主题分类、审计、评分与报告验证思路；`sector_taxonomy.json` 为适配版本并保留来源字段 |
| illusionno/fund-analysis-matrix | MIT | 暗色看板、自选池和图表交互思路 |
| simonlin1212/vibe-astock | Apache-2.0 | 硬指标/AI 分离、实际输入体检和结构化输出思路 |
| zhangsensen/etf-rotation-strategy | MIT | 多层验证、迟滞、市场状态门控和参数冻结思路；不自动克隆，见安全说明 |
| hsliuping/TradingAgents-CN | 混合许可证和项目特定条款 | 仅研究 Provider/配置/容器架构；未复制受限前后端源码 |
| fadaiba/a-share-etf-rotation | 未确认明确许可证 | 仅研究聚类和风险建模思路，不复制源码 |
| DIYgod/RSSHub | AGPL-3.0 | 可由用户单独自建 RSS 服务；本项目只消费标准 RSS/Atom，不捆绑 RSSHub |
| wukan1986/ta_cn | MIT | 中国市场技术指标与筹码分布研究参考；ETF/LOF 采用独立实现的成交量价格分布近似，并显式标记 estimated |
| bukosabino/ta | MIT | ADX/DMI、MFI、CMF、OBV、CCI、Williams %R 等标准指标公式/测试口径参考 |
| Travisun/Opptrix | Apache-2.0 | RSRS high~low OLS、beta×R²、滚动 z-score 口径参考 |
| Super-YYQ/stock_selector | 未声明许可证 | 仅参考公开策略说明中的箱体/海龟/RPS/价量回踩条件，不复制源码 |

## 重要提醒

- 用户的个人私用意图不自动覆盖上游许可证、署名要求或数据服务条款。
- 本包不包含第三方仓库完整源码。可选浅克隆清单见 `vendor/manifest.json`；个人研究 opt-in 只下载到隔离目录，不将其转许可为本项目代码。
- `zhangsensen/etf-rotation-strategy` 的最新提交说明其历史快照曾含旧凭据，因此本项目不在生产服务器自动克隆该仓库。
- 行情和新闻数据的展示、缓存、再分发权利与代码许可证是不同问题，应遵守数据源合同。
