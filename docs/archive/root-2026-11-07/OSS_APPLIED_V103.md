# v1.0.3 开源吸收落点与未完成项

延续[原始选项及逐文件审阅](archive/planning-v1/OSS_ABSORPTION_20260906.md)，不把参考、复制源码、安装成功、真实任务通过混为一谈。以下是本项目落点，不声称本轮运行了全部上游。

| 用户选定项目 | 参考源码/位置 | 本项目落点 | 本轮状态 |
|---|---|---|---|
| KairoTrend (https://kairotrend.com/) | 用户提供截图的信息结构 | Vue侧栏/账户；原模板仍在同一总览 | 保留，不复制商业品牌或私有源码 |
| Vibe-Research (https://github.com/simonlin1212/Vibe-Research) | 固定09e8404a33ba0d05e036e01207be4701c61d692c；orchestrator/src/runner.ts、run.ts、LICENSE | scripts/vibe_trial.py、bridge/、external_reports、AISetupGuide.vue | 隔离安装器/报告导入既有，本版补配置引导；真实安装登录与研究交本地 |
| TradingAgents (https://github.com/TauricResearch/TradingAgents) | tradingagents/default_config.py、研究角色 | 证据→反证→风险模板；不替换current action | 方法参考，未加整套运行依赖 |
| QuantDinger (https://github.com/OpenByteInc/QuantDinger) | docs/architecture/PROCESS_ROLES_AND_TASKS.md | 单worker、有界任务、失败/租约和日志 | 工程思想；前后端许可分开，不复制前端品牌 |
| tick-stock-panel (https://github.com/shy3130/tick-stock-panel) | frontend/src/components/Layout.tsx、docs/factor-platform-plan.md | FavoriteButton共享状态、目录/图表统一入口、因子勾选诊断 | 交互参考；许可矛盾未澄清的资源不复制 |
| deepseek-harness-quant (https://github.com/yuanwang589-dev/deepseek-harness-quant) | factors/pool/registry.py、etf/etf_map.py、risk/factor_attribution.py、assets/skills | 因子候选与相关性诊断、人工复盘的当时证据绑定 | 方法参考；没有自动进化/生产参数热改 |
| KHQuant Skill (https://github.com/khscience/khquant-skill) | SKILL.md | 查询/写入/危险操作区分、后续回测对照 | 独立软件依赖未安装，不当行情源 |

本版实际新增文件：workspace/index_history.py、workspace/journal.py、providers/index_history.py、frontend/src/stores/favorites.ts、AISetupGuide.vue、ManualReview.vue、HistoryLoader.vue、scripts/archive_market_history.py。原 WorkBuddy HTML/CSS/指标渲染继续使用，不用开源新面板替换用户原模板。

Vibe 的固定版本属于 TS 编排/React/Python 组合，不能拿当前 main 的新目录或模型适配推断固定版本支持。安装器会固定提交并核验；升级另做审阅。先用它适合的市场证据与日报任务，不把公司财务六阶段直接套给 ETF。

用户允许先下载学习，但本容器没有普通网络安装能力，也没有用户模型登录。本轮没有把完整上游源码复制进生产或宣称已安装。可执行的本地安装/停止点见 [本地接收](LOCAL_ACCEPTANCE_V103.md)。上游归档必须独立环境、保留 LICENSE/NOTICE、先检查再启动；不导入凭据、自动交易进程、任意Shell插件或生产数据库访问。

人物 Skill 仅是公开材料形成的假设模板；模板目录和资产目录分开核对，不采信收益宣称。因子数量不是独立信息数量，选择因子不会自动给出未来上涨概率。
