# ETF 14:30 开源工程研究

本工程没有整仓替换当前 FastAPI/PostgreSQL 架构，而是采用“核心逻辑原生实现 + 外部项目作为独立第二实现”的方式。

| 项目 | 借鉴点 | 接入边界 |
|---|---|---|
| `waditu/czsc` | 分型、笔、线段、中枢、信号—事件—交易抽象 | 仅作为完整缠论对账；当前页面继续标记 `chan_zone_approx` |
| `klinecharts/KLineChart` | 专业蜡烛图、指标副图、画线与标记 | 当前版本使用无 CDN Canvas；后续可替换图表层 |
| `apache/echarts` | 区间、热力图、概率和回测可视化 | 不用于计算交易指标 |
| `zhangsensen/etf-rotation-strategy` | 排名迟滞、最短持有、风险门控 | 任何参数变化必须重新 walk-forward |
| `akfamily/akquant` | 独立事件回测、因子表达式、walk-forward | 第二回测引擎，不替换当前引擎 |
| `Nixtla/mlforecast` | 多 ETF 全局时间序列模型 | 隔离研究，不能自动晋升生产 |
| `scikit-learn-contrib/MAPIE` | Conformal 区间 | 用真实 Holdout 对预测区间做第二实现校准 |
| `stefan-jansen/alphalens-reloaded` | IC、Rank IC、分位收益、换手 | 用来删除无增量指标 |
| `wukan1986/ta_cn` | 中国公式和成交成本分布 | ETF 中只称成交密集成本近似 |
| `BatuhanUsluel/Algorithmic-Support-and-Resistance` | 历史拐点聚类为区域 | 本项目采用确定性聚类，仍需真实触及率验证 |

第三方许可证和 NOTICE 必须保留。外部仓库中的密钥、账户或历史配置不得复制。
