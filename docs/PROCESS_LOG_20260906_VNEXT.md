# 本轮学习与文档修订过程记录

日期：2026-09-06；轮次：用户提供Kairo截图及新开源项目后的vNext规划。
基线：`Jovifei/ETF-Fund-Analysis@3c7bdc7ff36b3dea482651e087127a33c4974903`。

## 1. 输入与范围

直接输入：本轮用户文字、Kairo截图、五个指定工程、KHquant线索、三个抖音链接。最终明确范围为“先学习和规划，还不需要执行”。因此未安装、未部署、未启动定时、未调用模型分析或任何交易接口；只读取公开资料与仓库，编写文档。

本轮工作目录是会话沙箱，不是用户电脑的磁盘，也不是阿里云。GitHub文档交付与用户本地同步是两件事；不能声称已修改用户电脑。截图包含账户信息，不进入公开仓库/文档包。

## 2. 实际阅读范围

- 现有工程：AGENTS、STATUS、HANDOFF、docs索引及旧方案；定向读取ReviewService、WatchlistService，确认可复用边界，不声称全代码重新审计。
- TradingAgents：README、LICENSE、default_config.py。
- QuantDinger：README、LICENSE、PROCESS_ROLES_AND_TASKS.md。
- Vibe：固定commit的README、LICENSE、run.ts、runner.ts。
- tick：README、LICENSE、factor-platform-plan.md、Layout.tsx。
- DSHQuant：README、LICENSE、树、factor_engine、registry、factor_attribution、etf_map、两份niu-san Skill。
- KHquant：搜索定位khscience/khquant-skill，直接读取Skill和LICENSE，并打开官网；发现搜索摘要与Skill版本说明不同。
- 补充检索：tradermonty的低频研究工具集，直接读取Druckenmiller式Skill、portfolio-manager与LICENSE。
- 官方Codex文档：非交互模式、认证、SDK。完整来源和已知blob见开源审阅。

只阅读相关文件/段落；性能、收益、全量测试、所有依赖/资产版权和安装可靠性未被本轮验证。

## 3. 无法核实的材料

Kairo官网可读；应用dashboard未返回可读内容，未操作其登录后交互。三条抖音user/self链接和对应video路径均无法取得可读视频内容：
- `7679300031819566336`：用户用于说明Vibe。
- `7657420637393132901`：用户用于说明KHquant。
- `7674552793218272558`：用户用于说明因子/持仓/风格。

以上对应关系来自用户描述，不是视频验证结论。“张萌”是否指章盟主保留待确认。没有逐帧动效/字幕证据，未把搜索摘要当视频内容。旧Share链接未取得的原文仍保留旧记录，不新增“读完”声明。

## 4. 重要修订与原因

| 修订 | 原因/证据 | 本轮结果 |
|---|---|---|
| 顶部四入口 → Kairo左栏目标 | 用户本轮截图与描述 | UI目标稿，现有路由不变 |
| 新增可选AI与因子研究目标 | 用户明确需求 | 不能再用“不堆页面”否决 |
| UI与验证分两线 | 页面交付和预测资格是不同验收 | 原型/ETF闭环可先做，未校准继续标注 |
| 本地Vibe先于整套多Agent部署 | run.ts/runner.ts有清楚产物与隔离边界 | 规划首个独立试点，未安装 |
| 保留旧主站核心 | 现有快照/权限/审阅可复用 | 不迁框架，不造第二current action |
| 持仓分析分类 | 个人成本/ETF穿透/机构披露不是同一因子 | 分层设计、数据可见时间约束 |
| 风格Skill存在≠本人/收益复刻 | 上游Skill是公开资料与假设流程 | 只作方法论候选 |
| 123+不是验收数量 | 同义因子、外部manifest、未实测覆盖 | 首批小池，逐项OOS |
| 许可证以文件为准 | TradingAgents实际Apache2；tick声明冲突 | 记录不确定项，不复制受限资源 |

旧UI/路线图/总交接原文通过基线commit永久链接保留，新入口只维护一套目标。代码现状与用户目标冲突记为差距，不判定需求已取消。

## 5. 文件处理清单

新增：`planning/ETF_WORKSPACE_VNEXT.md`、`research/OSS_ABSORPTION_20260906.md`、`planning/LOCAL_RESEARCH_BRIDGE.md`、`planning/FACTOR_SKILL_GOVERNANCE.md`、本文。

更新：`docs/README.md`、`docs/UI_UX_CONTRACT.md`、`docs/ROADMAP_TO_FINAL.md`、`docs/PROJECT_HANDOFF_20260906.md`、根`STATUS.md`、`HANDOFF.md`。

保留：AGENTS安全边界、现有应用/配置/数据库/调度代码、历史发布和专题验证记录。没有复制任何上游源码/许可证正文作为运行依赖。

## 6. 文档验收与后续过程要求

本轮检查文档相对链接、Markdown代码围栏、UTF-8/尾部换行、需求ID、范围与“未实施”标记、认证关键字和凭据模式；逐文件SHA256可在交付包清单核对。外部URL内容只核查已读取部分，不把未审阅链接称为全量链接检测通过。GitHub PR/CI结果以该PR实际状态为准，不引用上轮测试冒充本轮。

下一次Agent每次只接一个M阶段/需求ID：记录基线 → 权限/许可证/版本核查 → 失败测试/复现 → 修改 → 本地/CI/浏览器证据 → 完成/缺口 → 回滚。未获用户授权进入M1前，仍停留在方案评审。后续安装还需记录OS/CPU/RAM、数据源范围、峰值资源、模型费用和可卸载性。
