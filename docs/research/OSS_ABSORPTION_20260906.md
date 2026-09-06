# 开源项目吸收审阅：ETF低频研究工作站

审阅日期：2026-09-06。方法：README、许可证、选定实现文件与已有工程交叉阅读，**非全仓安全审计，未安装/运行上游**。可运行性、资源消耗和真实ETF覆盖仍需隔离试点验证。可变main/master链接应在实施前固定commit并核对本页内容锚点。

## 1. 结论矩阵

| 项目 | 适合吸收 | 接入方式建议 | 不照搬 | 顺序 |
|---|---|---|---|---|
| KairoTrend | 左侧栏、顶部搜索、底部账户、暗色低装饰壳 | 按用户截图独立实现 | 品牌、付费/邀请、未核实动效或私有源码 | UI首要参考 |
| Vibe-Research | 本地Codex编排、证据/计算/冲突/报告、日复盘/新闻线索 | 独立本地工作站+产物适配 | 把公司六阶段直接套ETF、复制全局凭据 | 首个本地试点 |
| deepseek-harness-quant | 因子生命周期、ETF映射/相关性、持仓归因、交易风格Skill | 研究隔离模块/方法迁移 | 自进化自动上线、直接接实盘、未验证因子权重 | 因子/风格重点 |
| tick-stock-panel | 行情卡、折叠导航、因子库/检验/相关性与候选流程 | UI结构与统计契约借鉴 | 高频tick/全市场扫描、整套前端多菜单 | UI/因子参考 |
| TradingAgents | 技术/新闻/多空反证/风险角色、受限讨论、检查点 | 按需研究模板或隔离runner | 另一个权威买卖引擎、全天多Agent扫描 | AI按需增强 |
| QuantDinger | 有限任务与常驻进程分离、任务状态/版本/监控 | 设计借鉴，必要时隔离试用 | 实盘worker、双Redis+Celery整套基础设施、付款系统 | 架构参考 |
| khquant-skill | kh CLI工作流、查询/修改/危险动作分级 | 将来独立回测工具适配 | 误认为Skill本身含引擎/数据权利，直接覆盖AGENTS | 次级验证工具 |
| tradermonty/claude-trading-skills | 低频复盘/风险复核/风格方法模板 | 单个Skill审阅改写 | Alpaca连接和未经ETF适配的美股阈值 | 补充发现 |

这是“吸收模块和合同”，不是“安装八个网站再用iframe拼接”。保留我们已有FastAPI/PostgreSQL16、用户隔离、ProviderAudit、指标/预测/动作/SR快照及审阅候选。

## 2. Vibe-Research：最适合先打通本地研究结果

仓库：https://github.com/simonlin1212/Vibe-Research
固定审阅提交：`09e8404a33ba0d05e036e01207be4701c61d692c`；LICENSE为MIT。

已读：README前270行、LICENSE、`orchestrator/src/run.ts`、`orchestrator/src/runner.ts`。上游使用TS编排器、React/Vite界面、Python数据/计算工具和官方Codex SDK，不是重训练一套模型。

**最有价值**：运行/阶段状态、输入证据、确定性计算校验、冲突信息与报告分离；run.ts输出JSON进度结果，0/2/3区分完整/不完整或过期/失败。runner.ts把run与thread、阶段与turn映射，提供事件记录、超时、环境脱敏及产品CODEX_HOME隔离。可作为研究桥接的真实技术起点，而不只抄截图。

README列出日报、新闻雷达、产业线索、研报档案、持仓/自选等能力；其完整公司深研以A股为核心。**这些是上游能力说明，不代表每类任务已被我们验证或都有相同CLI入口。** ETF阶段优先使用市场复盘/事件证据和我们提供的技术快照，股本、财务和公司估值流程留给个股阶段。

未来本地试点需按其固定版本检查Node（README要求至少22.18，建议24）、Python（至少3.11，示例3.12）、Codex固定版本及脚本。README描述的本地端口为API8765、前端5930；端口冲突、权限、启动脚本需本地验收。运行数据放其独立.local目录；不整目录同步到云端。模型调用费和资源是待测项。

源码锚点：
- https://github.com/simonlin1212/Vibe-Research/blob/09e8404a33ba0d05e036e01207be4701c61d692c/orchestrator/src/run.ts （blob `068ad46d4d8d0839481ae90b338476a49f738396`）
- https://github.com/simonlin1212/Vibe-Research/blob/09e8404a33ba0d05e036e01207be4701c61d692c/orchestrator/src/runner.ts （blob `4c8dd54671f2a6aa80343b8d126bc0be28d2c69e`）
- https://github.com/simonlin1212/Vibe-Research/blob/09e8404a33ba0d05e036e01207be4701c61d692c/LICENSE

## 3. deepseek-harness-quant：ETF相关性、因子治理与风格候选

仓库：https://github.com/yuanwang589-dev/deepseek-harness-quant （默认master）
LICENSE为MIT，附研究/教育用途说明；第三方依赖、数据与各Skill素材仍需分别审阅。

已读README、仓库树、LICENSE、`factors/factor_engine.py`、`factors/pool/registry.py`、`risk/factor_attribution.py`、`etf/etf_map.py`的相关段落、两份niu-san Skill。

**值得直接研究的实现**：
- 注册表用candidate/evaluating/active/monitoring/retired与locked区分自动评估和人工裁决；可移植生命周期思想，不能把它的SQLite直接接生产。
- ETF映射比较策略收益与ETF收益的全期/分年/滚动相关、beta、流动性，并排除冗余ETF。这非常符合低频主观配置，但上游40日调仓、top20等设置不是我们的新默认。
- 归因把历史决策记录和后续收益连接，可用于复盘，但我们需要decision_id级别样本、防止同代码多次决策错配。
- `niu-san-distillation` 给出公开证据→可计算假设→相关性/回测→保留或证伪的流程；不是“模仿名人即可赚钱”。目录中确有章盟主等风格Skill。

**源码揭示的限制**：核心factor_engine中`rps_120`与`mom_120`都计算120日涨幅；不能把因子名字数当独立信息数。归因代码依赖`data/factorpool/output`外部manifest；部分Skill提到的旧工作区路径需要逐项核对。README自述123+不等于当前公开包全量资产和数据开箱齐备；本轮没有运行其全量数据验证。样例/合成数据也不能成为我们的ETF有效性证据。

未来隔离试点在Vibe之后；独立Python环境和私有数据目录，先检查所有输入文件是否齐备，再跑少数因子/ETF映射；不启动自进化、参数热改、交易桥或自动发布。

源码锚点：
- https://github.com/yuanwang589-dev/deepseek-harness-quant/blob/master/factors/factor_engine.py — blob `bb979298168798abe43275398ab959ea37230a43`
- https://github.com/yuanwang589-dev/deepseek-harness-quant/blob/master/factors/pool/registry.py — blob `427c2e74b36028319827eec47a08d2e68fcbd94f`
- https://github.com/yuanwang589-dev/deepseek-harness-quant/blob/master/risk/factor_attribution.py — blob `00337d2648f3e19980192023beb2b6b92115eee8`
- https://github.com/yuanwang589-dev/deepseek-harness-quant/blob/master/etf/etf_map.py — blob `c66bc3a4113f8c33dbdd1d8c4d4a3487fb33e61e`
- https://github.com/yuanwang589-dev/deepseek-harness-quant/blob/master/assets/skills/niu-san-distillation/SKILL.md — blob `c6a3a6d9930204cb428e974898f5110b44607380`
- https://github.com/yuanwang589-dev/deepseek-harness-quant/blob/master/assets/skills/niu-san-zhangmengzhu/SKILL.md — blob `b25b4a2811690eb9688aead9b720ac15fc4fedd5`

## 4. tick-stock-panel：展示与因子研究的重点参考

仓库：https://github.com/shy3130/tick-stock-panel
已读README前220行、LICENSE、`docs/factor-platform-plan.md`前150行、`frontend/src/components/Layout.tsx`前155行。

Layout.tsx使用侧栏导航、共享查询/行情状态、桌面判断、主题切换，且品牌色与功能语义色分离。我们吸收这些组织方式，不复制它十几个一级菜单。总览采用市场状态/板块/自选表，ETF详情使用同一对象视图，因子页借鉴“目录—检验—组合—候选”而不是再造一套首页。

因子文档明确区分研究线与交易线，描述相关性剪枝、嵌套样本外、统计检验和显式候选；近期执行记录把目录扩到77，而README保留其他旧数量。这说明上游也存在文档版本差异，不能把某个数字作为交付指标。其自动挖掘/DSL完整平台可以研究，首版只做少量白名单因子，不开放任意Python执行。

**许可证待澄清**：根LICENSE是MIT，但README同时写“仅供学习研究/严禁商业用途”。本轮只借鉴设计，不对矛盾作法律结论；逐文件复用前明确作者许可、素材和依赖条款，不能凭一个MIT徽标宣称全资源无限制。我们虽个人使用也保留署名。

源码锚点：
- https://github.com/shy3130/tick-stock-panel/blob/main/frontend/src/components/Layout.tsx — blob `d2926cbbe111edf5ffa4ac8716890ab4c9f04473`
- https://github.com/shy3130/tick-stock-panel/blob/main/docs/factor-platform-plan.md
- https://github.com/shy3130/tick-stock-panel/blob/main/LICENSE — blob `6d33010c43faf27c06eb516cb519add564a887ad`

## 5. TradingAgents：吸收研究角色，不替换权威动作

仓库：https://github.com/TauricResearch/TradingAgents
本次根LICENSE实读为**Apache-2.0**，不要凭旧印象写MIT。已读README和`tradingagents/default_config.py`。

借鉴技术、新闻/情绪、基本面、看多/看空反证、风险总结以及检查点/重试上限。我们的第一版可缩成“技术证据+新闻+反证/风险”按需分析，无需全池多轮辩论。

配置文件显示讨论轮数、token/retry预算、checkpoint与vendor链可配置；默认数据/宏观上下文偏海外（如yfinance/FRED及美股基准），且上海符号常为.SS。不能原样用于.SH ETF，更不能把LLM生成的交易决策覆盖我们的canonical action。ETF基本面要改成指数/费率/规模/流动性/持仓结构，不拿基金当公司算财务。

未来适配方式：单独runner/只读证据provider，固定版本，先最小角色，再比较额外讨论是否真正增加信息。任何实盘/券商能力不进入主站。

源码锚点：https://github.com/TauricResearch/TradingAgents/blob/main/tradingagents/default_config.py — blob `6a35f472eab82d17981417c352841c735bf037f0`；LICENSE blob `261eeb9e9f8b2b4b0d119366dda99c6fd7d35c64`。

## 6. QuantDinger：工程边界有价值，完整部署不合首阶段预算

仓库：https://github.com/OpenByteInc/QuantDinger
根LICENSE实读Apache-2.0。已读README前210行和`docs/architecture/PROCESS_ROLES_AND_TASKS.md`。

该工程的API、迁移、交易、scheduler、Celery worker/beat分工明确，任务lease/heartbeat及缓存Redis与任务Redis分开很有参考价值。**但完整生产栈含真实交易责任和多进程基础设施**，不应因为功能丰富就迁到我们的小服务器。

吸收有限任务的持久化/重试/进度、输入参数版本、研究与执行边界；初期用既有PostgreSQL任务表与一个本地runner满足规模，只有压测确证后才增加消息中间件。前端图表及第三方资产许可尚未逐项审阅，不宣称整套图表可自由复制。README一键安装命令不在本轮执行。

源码锚点：https://github.com/OpenByteInc/QuantDinger/blob/main/docs/architecture/PROCESS_ROLES_AND_TASKS.md — blob `4cf606d9aa6a4a097f4b84529fa7a714b8d5e1d1`；LICENSE blob `2adf5b861d20f6fe93f181b146f1f35254c741d0`。

## 7. KHquant：Skill找到了，Skill与平台必须分开

仓库：https://github.com/khscience/khquant-skill
官网：https://khsci.com/khQuant/
根LICENSE为MIT。已读SKILL.md相关段落与LICENSE；Skill将自然语言路由到`kh`配置、数据、策略、回测和结果查看，并要求对修改/危险命令确认。

搜索索引的README仍主要写v3.3.6.1；本轮直接读取的SKILL.md已讨论v3.4.0、网页回测和平台分发差异。**实施时以固定源码、实际kh version/help和平台授权为准，不拿旧搜索摘要做安装依据。** Skill不是回测引擎、不是行情授权，也不等于所有桌面安装包都公开可分发。当前Skill中对Windows/macOS V3与Linux的交付边界有不同说明，必须再核实目标系统对应的安装资格。

建议仅作为后续第二回测视角：把相同ETF数据、交易日、复权、费用和持有规则输入，比较结果而非追求“多一个系统”。不接miniQMT/xtquant实盘，不照抄让AI回显凭据的命令模式。

源码：https://github.com/khscience/khquant-skill/blob/main/skills/khquant/SKILL.md；LICENSE blob `ea6006b96ecdb17a19fdde7f5345b306af077e7a`。

## 8. 补充开源检索：低频复盘与交易方法Skill

仓库：https://github.com/tradermonty/claude-trading-skills ，根LICENSE实读MIT。

其项目定位明确面向时间有限的ETF/长期投资者与有纪律的波段流程，不以外包买卖决定为目标。已直接读 `skills/stanley-druckenmiller-investment/SKILL.md`：它消费多个研究JSON汇总方法论；读 `skills/portfolio-manager/SKILL.md`：默认获取持仓依赖Alpaca，不能直接装到本系统。

可优先研究交易复盘、风险清单、证据记忆，再做中国ETF适配。命名为某投资者风格不构成该投资者认可；美股数据源/阈值/可交易品种不直接迁移。更多未直接读取源码的搜索结果不列为已审计或推荐安装。

源码锚点：
- https://github.com/tradermonty/claude-trading-skills/blob/main/skills/stanley-druckenmiller-investment/SKILL.md — blob `71b58b1e8051306bc7468684c1b259e6ebef3304`
- https://github.com/tradermonty/claude-trading-skills/blob/main/skills/portfolio-manager/SKILL.md — blob `7c294c2b190d7e56f0374d4bc5fd25bb4a1687a7`
- https://github.com/tradermonty/claude-trading-skills/blob/main/LICENSE — blob `f04a7bced8bb1f03ce92fbdc6912594b0c37d3c0`

## 9. 视频、网站与证据边界

用户三条抖音链接的modal_id为 `7679300031819566336`、`7657420637393132901`、`7674552793218272558`。本轮访问原user/self链接及对应/video路径均未获取可读视频内容；不能声称看过演示、字幕或核实人物/因子数量。保留为待补证输入，将来提供字幕/截图时只补其差异，不推翻已确认用户目标。

Kairo官网可读，`/app/dashboard`未返回可读应用内容，不能据此声称操作过登录后页面或逐帧复刻动效。用户提供截图足以定义壳层；截图含个人信息，不把原图写入公开仓库。

## 10. 复用准入与下一次行动

每个吸收项记录：需求ID、上游commit/blob、文件范围、许可证/NOTICE、数据许可、依赖/网络、输出contract、测试、资源测量、回滚、owner。只复用设计与少数可测模块；源码复制须保留许可证并审阅第三方条款，不import整个vendor源码树到生产。

先按 [总方案](../planning/ETF_WORKSPACE_VNEXT.md) M1做可评审壳层；部署授权后M3只运行Vibe隔离试点。DSHQuant/TradingAgents/KhQuant分批引入，不同时启动多套runner。详细桥接见 [研究包合同](../planning/LOCAL_RESEARCH_BRIDGE.md)。
