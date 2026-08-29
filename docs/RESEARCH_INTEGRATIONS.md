# 研究集成资格（Research Integrations）

## 概述

v0.7.0 支持多个可选研究库，用于因子分析、预测校准、组合优化和第二回测引擎。所有集成遵循以下治理原则：

- **候选模型不自动晋升**；只有人工 approve 才能改变 `calibration_status`
- **研究输出为纯 JSON**；不直接修改生产数据库中的预测或信号
- **实时链路不依赖未资格的集成**；qualified 状态需要至少 3 个月真实数据验证

## 集成状态分类

| 状态 | 含义 |
|---|---|
| qualified | 已通过真实数据资格验证，可进入生产链路 |
| available | Python 可 import，但尚未通过资格验证 |
| unavailable | 未安装或安装失败 |
| unqualified | 已安装但未通过资格验证（保留隔离研究） |
| research_only | 仅用于研究；不进入实时生产链路（默认隔离） |

## 按功能分组

### 因子分析

- **alphalens-reloaded**（`research_only`）：因子 IC/分位数收益/换手分析。由 `analyze_factors` 任务使用。
- **exchange_calendars**（`qualified`）：XSHG 交易日历，生产运行时使用。

### 预测校准

- **MAPIE**（`unqualified`）：区间预测校准参考。本系统使用 `local_conformal_research_v1` 自建走廊；MAPIE 保留隔离研究。
- **MLForecast**（`research_only`）：全局特征管线候选。

### 全局模型

- **LightGBM**（`research_only`）：全局分位模型（p_up/terminal/path）。由 `research_global_models` 任务创建候选。
- **CatBoost**（`research_only`）：LightGBM 备选；未安装时自动降级。

### 组合优化

- **Riskfolio-Lib**（`research_only`）：HRP/风险平价/CVaR 优化。由 `optimize_portfolio` 任务使用；输出纯研究建议。

### 独立第二引擎

- **AKQuant**（`unqualified`）：独立第二回测引擎候选。待真实数据后对账。
- **RQAlpha**（`unqualified`）：中国 A 股独立第二引擎候选。待真实数据后对账。

### 隔离研究（不进入生产链路）

- **Qlib**（`research_only`）：量化研究平台参考。
- **FinGPT**（`research_only`）：金融 NLP 参考（未注册于代码）。
- **vectorbt**（`research_only`）：向量化回测参考（未注册于代码）。
- **RD-Agent**（`research_only`）：研究自动化参考（未注册于代码）。

## 注册表

运行时集成状态记录在 `config/integration_registry.json`。运行 `research_capabilities` 任务可获取当前可用状态。

## 资格要求

合格（qualified）需要满足以下全部条件：

1. 无破坏性 bug（在测试中已验证）
2. 至少 3 个月真实数据运行（影子运行 ≥20 个交易日后开始计时）
3. 与 baseline 在至少 3 个 rolling window 中稳定比较
4. 不引入新的安全边界突破（无 Shell/DB 写入/网络抓取权限）
5. 人工 approve 记录完整
