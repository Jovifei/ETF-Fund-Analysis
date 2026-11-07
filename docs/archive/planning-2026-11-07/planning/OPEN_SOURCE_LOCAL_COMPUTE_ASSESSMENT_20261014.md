# 开源参考与本地计算架构评估 — 2026-10-14

状态：RESEARCH_CANDIDATE，非功能验收收据。原Agent草案保存在a9661ff历史；本次按主仓核验修正许可证和过度完成声明，不移植策略、不启用交易、模型或私有数据回传。

## 主源核验与取舍

| 项目 | 2026-10-14核验 | 当前决定 |
|---|---|---|
| [quant-fletch](https://github.com/AbelTami/quant-fletch) | 主仓存在，GitHub标MIT；README描述日频ETF轮动、自研回测+VectorBT交叉验证、FastAPI/Nuxt及DuckDB/PostgreSQL | 仅作架构/PIT测试思路参考；README所称PIT安全尚未由本项目独立源码验证，不把它当可靠算法证明 |
| [Qbot](https://github.com/UFund-Me/Qbot) | 主仓存在；GitHub识别MIT，但README LICENSE段仍有CC BY-NC-SA4.0说明，与原草案Apache-2.0不一致 | 移植具体文件前核实际LICENSE/NOTICE及范围；只讨论分层/运行记录，不引入实盘接口或整个平台 |
| [streametf](https://github.com/yingxincui/streametf) | 主仓存在，GitHub未识别许可证；不能直接标MIT | 可阅读公开设计，不自动复制代码，许可明确后另评 |
| qstock | 原草案没有精确仓库/固定版本 | PENDING_IDENTITY，不据名字移植或新增依赖 |

本项目首期继续Python确定性计算、SQLite、现有ProviderAdapter、Windows任务、签名有界展示包；不为参考资料提前引入DuckDB双库/Prefect控制平面。指标、预测、评级与回测由确定性代码计算，LLM最多解释冻结的研究证据，不执行行情抓取/数据库工具或交易。

## 当前实际工作与未完成边界

- 已有本地采集计算与公网展示包代码；正式数据范围、实际版本与运行收据以docs/audits/MAIN_CONSOLIDATION_20261014.md为准。旧草案的34只/全部完成数值不能当最新验收。
- 当前纳入market_context本机任务、包part和读取接线，意在补顶部指数卡片来源。代码合入不等于所有指数真实权限/时点/量额合格；空数据/故障回退、generation pin和端点同代语义仍需测试/上线验收。
- 未来本地复盘例程可记录当日输入、预测horizon与其真实实现后收益、成本/基准/样本外方法；不得用尚未实现次日收益填当日胜率或把回测收益当可执行收益。
- 私人持仓/自选反馈回传本机属于新增私有权限边界，未经Jovi明确许可不建立接口或赋producer读权限。
- 秘密不进入代码/日志/GitHub/GPT。未知许可/PIT/OOS保持UNKNOWN、not_calibrated、actionable=false；无自动交易。

后续顺序：先完成已有本机到网站链路的来源/时点/同代/云端写退休验收，再评估算法和复盘功能；开源项目可借鉴，不能用主仓宣传替代本项目验证。