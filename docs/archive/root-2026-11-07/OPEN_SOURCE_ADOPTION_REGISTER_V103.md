# 开源借鉴登记册（v1.0.3）

更新时间：2026-09-09  
原则：开源仓库提供设计参考或独立研究工具，不等于本项目运行时依赖、已经安装、真实任务通过或允许复制全部源码。每一项都要同时看固定 revision、许可证、数据服务条款、凭据历史和本项目的实际落点。

## 1. 总政策

本项目采用“核心逻辑独立实现 + 外部项目隔离借鉴”的路线：

- 运行时不直接 import `vendor/src` 里的参考仓库。
- `scripts/fetch_reference_sources.sh` 只浅克隆 `vendor/manifest.json` 中 `auto_fetch=true` 的固定 revision。
- `vendor/src` 不入 Git、不进 Docker build context、不进入 Python path、不存生产密钥。
- `--include-personal-use` 只是用户明确同意后的下载开关，不改变上游许可证、署名、数据和商业限制。
- 有凭据历史风险或许可证不清的仓库只读远程研究，不自动克隆到 ECS。
- 参考设计必须重新实现为本项目自己的数据合同和安全边界，不能把上游的自动交易、任意 Shell、全局模型权限带进来。

## 2. 已实际吸收的公开项目设计

| 项目 | 固定/审查版本 | 许可证或限制 | 借鉴点 | 本项目落点 | 运行边界 |
|---|---|---|---|---|---|
| `thincat75/fund-rotation-analyst` | `474e554f6d7f0219637883fd775c3df06b545fb1` | MIT | 采集→分析→渲染→校验；审计缓存；主题 taxonomy；多维基金评分；LLM 只解释 JSON | `ProviderAudit`、质量 hash、`sector_taxonomy.json`、主题/质量分、同一快照生成 HTML/JSON | 不复制源码；模型不能改确定性结果 |
| `illusionno/fund-analysis-matrix` | `2c68d2ec65c31ed61e1970a7f7c7383ac99fc6b9` | MIT | 暗色信息架构；自选 hydrate→刷新；详情 modal；BFF 隔离 | Vue 总览/目录/详情、自选同步、FastAPI 作为外部数据 BFF | 不直接采用其 React/Vite 运行时 |
| `simonlin1212/vibe-astock` | `d3af182b43aa75a5604ee467794ef7cfc70d1c01` | Apache-2.0 | 硬指标在代码；实际输入 preflight；结构化输出；降级提示；条件有效期 | `PreflightService`、证据来源/样本/校准提示、结构化 AI 合同、`expires_at` | Vibe 工具隔离；未宣称真实模型任务通过 |
| `zhangsensen/etf-rotation-strategy` | `4e5d1fbde56b0094db976cbebb6cf5020105bd98` | MIT；有凭据历史风险 | WFO→向量化→事件回测；迟滞；波动率/回撤门控；参数冻结 | 30 分钟状态迟滞、5 分变化门槛、市场暴露上限、版本/hash 和后续事件回测要求 | `auto_fetch=false`；不克隆完整历史到生产 |
| `hsliuping/TradingAgents-CN` | `74783e8817d6cf6de29867880631cc555153f36b` | 混合/项目特定条款 | Provider/模型配置、容器分层、报告状态 | 仅借鉴分层和配置思路 | 不复制受限前后端；个人使用不删除限制 |
| `fadaiba/a-share-etf-rotation` | `6e2a6e20b0a98f4b8a062aa40bf64da1c5d4b306` | 未确认清晰许可证 | ETF 聚类、多周期动量、风险平价研究 | 后续研究清单：避免高度相关 ETF 同时占仓、风险预算 | `auto_fetch=false`，不复制源码 |

## 3. 产品与工程参考项目

以下项目来自 v1.0.3 开源吸收记录，部分是界面或方法参考，并非 `vendor/manifest.json` 的运行时下载目标。

| 项目 | 参考内容 | 当前处理 |
|---|---|---|
| KairoTrend | 用户提供的研究信息结构、暗色和强调色布局 | 只保留原创信息层级；不复制商业品牌、图片或私有源码 |
| Vibe-Research | 固定 commit 的 TS 编排、研究产物导出和审核流程 | `scripts/vibe_trial.py`、`bridge/`、外部包预览已存在；真实登录/模型产物待本人操作 |
| TradingAgents | 研究角色、证据→反证→风险的分析模板 | 只吸收方法，不引入完整交易运行依赖，不覆盖 current action |
| QuantDinger | 任务分层、流程角色和失败处理 | 只借鉴工程思想；不复制受独立许可约束的前端 |
| tick-stock-panel | FavoriteButton、目录/图表入口、因子选择交互 | 仅作 UI 参考；许可矛盾资源不复制 |
| deepseek-harness-quant | 因子池、相关性、风险归因和资产/skill 分离 | 只形成候选诊断和人工复盘证据；不自动进化生产参数 |
| KHQuant Skill | 查询/写入/危险操作的分级 | 作为未来独立回测对照和工具治理参考，不当作行情源 |
| `waditu/czsc` | 分型、笔、线段、中枢和信号事件抽象 | 当前只保留 `chan_zone_approx`，完整缠论另做对账 |
| `klinecharts/KLineChart` | 专业蜡烛图、指标副图和标记 | 当前 Vue 使用 `9.8.12` 作渲染；指标计算仍由 Python 负责 |
| `apache/echarts` | 区间、热力图和回测可视化 | 可作为未来可视化参考，不计算交易指标 |
| `akfamily/akquant` | 事件回测、因子表达式、walk-forward | 注册为隔离第二引擎，状态 `unqualified` |
| `Nixtla/mlforecast` | 多 ETF 全局时间序列模型 | 研究候选，不能自动晋升生产 |
| `scikit-learn-contrib/MAPIE` | Conformal 预测区间 | 研究候选；当前 `local_conformal_research_v1` 不能冒充 MAPIE 校准 |
| `stefan-jansen/alphalens-reloaded` | IC、Rank IC、分位收益和换手 | `research_only`，用于删除无增量因子 |
| `wukan1986/ta_cn` | 中国公式和成交成本分布 | 只研究成交密集成本近似，不把它当真实成交成本 |
| `BatuhanUsluel/Algorithmic-Support-and-Resistance` | 历史拐点聚类为支撑/压力区域 | 采用确定性聚类，仍需真实触及率验证 |
| `microsoft/qlib` | 量化研究平台 | 只在数据和评估口径稳定后研究，不替代基础审计 |
| `dcajasn/Riskfolio-Lib` | HRP、风险平价、CVaR | 只输出研究建议，不写 Holding、不触发再平衡 |
| `ricequant/rqalpha` | 中国市场独立回测引擎 | `unqualified`，待真实数据对账 |
| `DIYgod/RSSHub` | 新闻聚合路由 | 不捆绑；只消费标准 RSS/Atom，独立部署需遵守 AGPL 和站点条款 |

## 4. 运行时依赖与资格状态

项目自身运行依赖在 `pyproject.toml` 和 `frontend/package.json`，其许可证在 `THIRD_PARTY_NOTICES.md` 和镜像 `THIRD_PARTY_LICENSES/` 中保留。研究集成状态在 `config/integration_registry.json`：

| 组件 | 用途 | 状态 | 是否生产运行时 |
|---|---|---|---|
| `exchange_calendars` | XSHG 交易日历 | `qualified` | 是 |
| `alphalens-reloaded` | 因子 IC/分位/换手 | `research_only` | 否 |
| `MAPIE` | 预测区间研究 | `unqualified` | 否 |
| `AKQuant` | 第二回测引擎 | `unqualified` | 否 |
| `RQAlpha` | 第二 A 股回测引擎 | `unqualified` | 否 |
| `mlforecast` | 全局序列候选 | `research_only` | 否 |
| `LightGBM` / `CatBoost` | 全局分位模型候选 | `research_only` | 否 |
| `Qlib` | 量化研究平台参考 | `research_only` | 否 |
| `Riskfolio-Lib` | 组合优化候选 | `research_only` | 否 |

“可 import”“已安装”“研究报告生成”三者都不等于 `qualified`。正式资格至少需要无破坏 bug、三个月真实数据、至少 20 个交易日 shadow run、多个 rolling window 对照、安全边界检查和人工批准。

## 5. 许可证、凭据和数据条款

### 5.1 许可证

项目自身代码使用 MIT，但 Python 包、Vue 依赖、图表库、外部脚本和参考仓库各自受自己的许可证约束。保留 `NOTICE`、许可证文本和上游 attribution；个人使用不是删除限制的开关。

### 5.2 凭据风险

`zhangsensen/etf-rotation-strategy` 的审查记录说明历史 sealed snapshot 可能残留旧 Token；即使 token 已失效，也不能把完整 Git 历史放到生产 ECS。任何仓库如果有硬编码 token、内网地址或未知认证目录，都只能远程阅读和手工重实现。

### 5.3 数据服务条款

AKShare、Tushare、FTShare、RSS 服务的“代码许可证”和“行情/新闻数据使用权”是两个问题。适配器能调用不代表可以无限再分发、长期缓存或作为商业服务出售；真实源、刷新频率和数据归档必须遵守各自条款。

## 6. 获取、审查和吸收流程

```text
登记项目和固定 revision
  → 读 LICENSE / NOTICE / README / 安全历史
  → 只获取允许的浅克隆或远程阅读
  → 记录借鉴文件和设计点
  → 用本项目自己的类型/Provider/任务合同重实现
  → 运行本项目测试、密钥扫描和许可证检查
  → 在知识库记录“借鉴了什么、没有复制什么、当前是否资格通过”
```

推荐操作：

```bash
./scripts/fetch_reference_sources.sh
./scripts/fetch_reference_sources.sh --include-personal-use
```

第二条命令不是默认权限，不会下载有凭据历史风险或许可证不明的项目，也不会改变运行时依赖。下载后的 `vendor/src` 必须继续保持隔离。

## 7. 下一步可借鉴方向

| 方向 | 参考项目 | 前置条件 | 不能提前做的事 |
|---|---|---|---|
| 14:30 事件回测 | AKQuant、RQAlpha、ETF rotation | 真实 PIT、费用/滑点和成交约束 | 不能用日线收盘拼接 14:30 |
| Forecast 区间校准 | MAPIE、mlforecast、Qlib | purged WFO、Holdout、泄漏检查 | 不能把研究候选标 calibrated |
| 因子有效性 | Alphalens、ta_cn | 足够 volume/amount、滚动窗口 | 不能用因子数量代替独立证据数量 |
| 组合风险 | Riskfolio、ETF rotation | 成分/相关性/风险预算的真实输入 | 不能自动写 Holding 或再平衡 |
| 图表增强 | KLineChart、ECharts、CZSC | 不改变后端数据合同 | 不能在前端重新计算 official action |
| 新闻扩展 | RSSHub | 独立部署和目标站点许可 | 不能将第三方新闻直接当事实无来源入库 |

## 8. 关联记录

- `vendor/manifest.json`：固定 revision、许可证、auto_fetch 和风险标记。
- `THIRD_PARTY_NOTICES.md`：运行依赖和参考项目声明。
- `docs/GITHUB_RESEARCH.md`：逐项目研究与实际落点。
- `docs/OSS_APPLIED_V103.md`：v1.0.3 已吸收/未吸收矩阵。
- `docs/RESEARCH_INTEGRATIONS.md`：运行时研究集成资格状态。
- `docs/LOCAL_ACCEPTANCE_V103.md`：Vibe、Codex、OCR 和真实源验收边界。

