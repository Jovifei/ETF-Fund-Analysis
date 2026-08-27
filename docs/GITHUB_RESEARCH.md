# GitHub 工程调研与落地记录

调研日期：2026-08-27。所有仓库状态会变化，以下 revision 是本次审查时观察到的版本。

## 结论

没有找到一个仓库能够同时满足：

- 中国 ETF/LOF；
- 稳定主备数据源；
- MACD/KDJ/持仓感知；
- 新闻证据；
- 1/5/20 日预测校准；
- 私有 Web 看板；
- 阿里云生产部署。

因此本工程采用“独立实现核心 + 隔离借鉴设计”的方式。运行时不 import 第三方项目源码，避免许可证、凭据、数据口径和升级风险耦合。

## 1. thincat75/fund-rotation-analyst

- Revision：`474e554f6d7f0219637883fd775c3df06b545fb1`
- License：MIT
- 地址：https://github.com/thincat75/fund-rotation-analyst

值得借鉴：

- 采集、分析、渲染、校验四段式流水线；
- 缓存不仅保存数据，还保存 provider、请求时间、质量哈希和失败原因；
- 基金评价分成持仓、风格、资金、交易质量等维度；
- 主题 taxonomy 用 exact + keyword rules；
- LLM 只解释证据 JSON，不修改数值和动作。

已落地：

- `ProviderAudit`；
- 数据质量哈希；
- `sector_taxonomy.json` 适配版；
- 主题分和基金质量分；
- HTML/JSON 报告由同一数据库快照生成；
- Codex 不得改变确定性结果的规则。

## 2. simonlin1212/vibe-astock

- Revision：`d3af182b43aa75a5604ee467794ef7cfc70d1c01`
- License：Apache-2.0
- 地址：https://github.com/simonlin1212/vibe-astock

值得借鉴：

- 屏幕上的主要读数由纯计算产生，AI 只负责叙述；
- 分析前检查实际输入对象，而不是检查“理论上有数据源”；
- 结构化输出有多级解析和安全失败；
- 降级数据必须在页面明显提示；
- 结论配套次日可验证条件，而不是无限期有效。

已落地：

- `PreflightService` 检查真实 bar/quote/forecast/news；
- Mock、非实时、过期或核心缺失阻断 actionable；
- OpenAI-compatible 输出经 Pydantic 校验；
- 信号有 `expires_at`；
- 页面显示退化来源、校准状态、样本数和区间。

## 3. zhangsensen/etf-rotation-strategy

- Revision：`4e5d1fbde56b0094db976cbebb6cf5020105bd98`
- License：MIT
- 地址：https://github.com/zhangsensen/etf-rotation-strategy

值得借鉴：

- WFO → 向量化回测 → 事件驱动审计；
- 多层结果不一致时不封版；
- 迟滞降低无效换手；
- 波动率/回撤门控动态降低总仓位；
- 参数冻结，防止研究配置与生产漂移；
- 因子方向和元数据贯穿管线。

已落地：

- 30 分钟状态迟滞和 5 分变化门槛；
- 510300 市场状态与 100/70/40/10% 组合暴露上限；
- 策略、指标、预测版本和输入哈希；
- 手工 walk-forward 预测验证；
- `CODEX_DEPLOYMENT_TASKS.md` 强制后续实现事件驱动审计。

安全发现：

该仓库最新提交专门清理过硬编码 Token 和内网信息，并说明历史 sealed snapshots 仍可能含旧凭据。即使旧 Token 已失效，也不应把完整 Git 历史或未扫描快照放到生产 ECS。因此 `vendor/manifest.json` 将其标记为 `auto_fetch=false`，只远程研究设计。

## 4. illusionno/fund-analysis-matrix

- Revision：`2c68d2ec65c31ed61e1970a7f7c7383ac99fc6b9`
- License：MIT
- 地址：https://github.com/illusionno/fund-analysis-matrix

值得借鉴：

- 暗色基金/股票卡片；
- 自选池先用持久化数据 hydrate，再刷新远程行情；
- 点击标的打开 K 线详情；
- BFF 隔离前端和外部接口。

已落地：

- 截图风格的暗色表格和卡片；
- 标的详情 modal；
- 浏览器定时刷新 + SSE；
- 外部数据全部由 FastAPI Provider Adapter 处理。

未直接采用 React/Vite，以减少个人 ECS 构建和运行复杂度；当前前端是无依赖原生 JavaScript/CSS。

## 5. hsliuping/TradingAgents-CN

- 地址：https://github.com/hsliuping/TradingAgents-CN
- License：混合许可证和项目特定商业条款

值得借鉴：

- Provider/模型配置抽象；
- FastAPI、数据库、缓存、前端和 Docker 的分层；
- 多模型供应商配置；
- 报告导出与任务状态。

本工程只借鉴架构，没有复制受限 `app/`/`frontend/`。即使用户是个人使用，也仍需保留上游许可证和遵守仓库声明；私用不是删除限制的技术开关。

## 6. fadaiba/a-share-etf-rotation

- 地址：https://github.com/fadaiba/a-share-etf-rotation
- 未确认明确 License

研究价值：聚类、动量、风险平价和 ETF 轮动组合。因许可证不明确，本工程不复制源码，仅把“避免高度相关 ETF 同时占仓”和“风险预算”列入后续研究清单。

## 7. AKShare / AKQuant / Qlib

- AKShare：https://github.com/akfamily/akshare
- AKQuant：https://github.com/akfamily/akquant
- Qlib：https://github.com/microsoft/qlib

使用：

- AKShare 已作为备用 Provider；
- AKQuant 的 walk-forward、因子和回测设计可作为下一阶段参考；
- Qlib 适合在数据和评估口径稳定后做高级模型，不适合一开始替代基础审计。

## 8. KLineChart / ECharts

- KLineChart：https://github.com/klinecharts/KLineChart
- ECharts：https://github.com/apache/echarts

它们适合后续把当前 Canvas 图升级成更强的金融图表。当前版本不引入 npm 运行依赖，以降低阿里云部署故障面；数据 API 已按日线数组设计，未来可直接替换前端图层。

## 9. RSSHub

- 地址：https://github.com/DIYgod/RSSHub
- License：AGPL-3.0

本工程不捆绑 RSSHub，只增加标准 RSS/Atom Provider。用户可在另一容器或另一服务器自建 RSSHub，然后把具体路由写入 `NEWS_RSS_URLS`。如果部署 RSSHub，应独立遵守 AGPL 和目标站点条款。

## 参考源码隔离与个人私用 opt-in

默认只拉取许可证清晰、已固定 revision 的仓库：

```bash
./scripts/fetch_reference_sources.sh
```

你已确认该系统仅个人私用，因此 helper 额外提供显式 opt-in，用于把带项目特定使用条款、但允许个人研究的源码放到隔离目录：

```bash
./scripts/fetch_reference_sources.sh --include-personal-use
```

该选项不会把第三方源码自动 import 到运行时，也不会改变上游条款。已发现凭据历史风险或许可证不明的仓库仍然不会由脚本下载。

只会浅克隆 `vendor/manifest.json` 中 `auto_fetch=true` 的 revision 到 `vendor/src`。该目录：

- 不入 Git；
- 不进 Docker build context；
- 不在 Python path；
- 不允许存放生产密钥；
- 仅用于人工比较和测试。
