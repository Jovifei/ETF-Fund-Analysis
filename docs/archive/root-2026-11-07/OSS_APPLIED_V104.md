# v1.0.4 用户选择的上游项目：源码与吸收

完整历史在 [v103登记册](OPEN_SOURCE_ADOPTION_REGISTER_V103.md) 与 [v103落点](OSS_APPLIED_V103.md)，不删除。下表不是“均已安装”清单；除许可允许的现有依赖外，本次没有把第三方完整交易栈复制进生产。

|项目/源码|本次吸收与落点|边界|
|---|---|---|
|KairoTrend https://kairotrend.com/|固定侧栏/账户/顶部搜索；原版快照保持在同一个主页|商业素材与私有源码不复制|
|Vibe-Research https://github.com/simonlin1212/Vibe-Research ，固定09e8404a33ba0d05e036e01207be4701c61d692c，orchestrator/src/runner.ts|具体读取AgentRunner/线程隔离/预算/证据事件；AISetupGuide实际CODEX_HOME/配对步骤，已有scripts/vibe_trial.py与Bridge|不拿main新能力当固定版现成功能；真实部署/登录见L4|
|TradingAgents https://github.com/TauricResearch/TradingAgents ，tradingagents/default_config.py|本轮再次读取provider/backend_url/model、输出预算、轮数、checkpoint；ai_profiles.py个人profile与事实/反证/风险、worker有界状态|不是将美股财务策略照套ETF；根后端许可证不自动覆盖其他项目资产|
|QuantDinger https://github.com/OpenByteInc/QuantDinger ，docs/architecture/PROCESS_ROLES_AND_TASKS.md|延续API/worker异步执行、持久任务/失败状态；配置保存与执行分离|前端QuantDinger-Vue独立source-available，不复制其前端代码品牌|
|tick-stock-panel https://github.com/shy3130/tick-stock-panel ，frontend/src/components/Layout.tsx|延续高密度筛选/星标和图表研究交互；原WorkBuddy表保留|README许可冲突未澄清的资源不复制|
|deepseek-harness-quant https://github.com/yuanwang589-dev/deepseek-harness-quant ，factors/pool/registry.py、etf/etf_map.py|小规模因子勾选、相关性与实际验证分离；复盘候选而非自动训练|人物模板/资产分开，不采信收益结论；全量多因子不是本期运行依赖|
|KHQuant Skill https://github.com/khscience/khquant-skill ，SKILL.md|查询/配置/执行分别授权，实际任务与测试收据|Skill不等于行情授权/独立回测软件已安装|

本次运行时继续使用KLineCharts进行图形渲染，周/月聚合及全部指标/辅助价位从服务端提供；没有调用图表内置指标替换后端公式。AKShare分类接口只在原Provider Adapter内使用，不在页面偷偷直连数据商。

外部协议参考（2026-09-10查阅）：
- https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create （token参数、JSON输出；结果仍须本地schema验证）
- https://developers.openai.com/codex/auth/ （官方登录与API认证区分）
- https://akshare.akfamily.xyz/data/fund/fund_public.html （ETF/LOF分类、行情端点；代码开源不等于数据商无限授权）

仓库链接/源码记录不是用户网络现场结果。需要先有完整上游副本时，按vendor manifest及许可在独立E盘目录抓取，不让其服务器、交易worker和本系统端口/数据库混在一起。三个未能读取的抖音视频仍只是需求线索，不新增虚假的观看证据。
