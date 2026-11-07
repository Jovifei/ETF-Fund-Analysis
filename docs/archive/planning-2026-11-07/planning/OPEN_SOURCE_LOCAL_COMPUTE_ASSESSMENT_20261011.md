# 开源算法本地计算评估 — 2026-10-11

状态：ASSESSMENT_ONLY / NOT_QUALIFIED。本批只核对公开一手来源及本地代码、编写方案；未运行算法测试、真实数据重放或生产操作。当前读取本地 HEAD 为 e722ad5d351da05ad01abfb7d5d2d339a6b75773，最终提交由父执行者填写。不是引入依赖或激活策略的收据。

## 仓库身份与固定版本

2026-10-11 通过 GitHub repo/commits API 核对默认分支 SHA、许可证元数据；许可证正文及下列源码/方法论为一手证据。SHA 仅固定评估对象，不表示已下载/执行。

|用户名称|核对候选/作者身份|固定 SHA|许可证与结论|
|---|---|---|---|
|etf-rotation-strategy|[zhangsensen/etf-rotation-strategy](https://github.com/zhangsensen/etf-rotation-strategy)，仓库 owner zhangsensen；项目现有研究文档已指向此仓库|fb74774af1bcaeffdcbb2b86954274b3b9b93295（master）|[MIT](https://github.com/zhangsensen/etf-rotation-strategy/blob/fb74774af1bcaeffdcbb2b86954274b3b9b93295/LICENSE)；身份可与现有引用对齐|
|AlphaLab|[Danielchen0101/Alpha_lab](https://github.com/Danielchen0101/Alpha_lab)，owner Danielchen0101；仅名称匹配候选|c014049715387775b480fd3bf1c20dcb3e8afc7f（main）|[MIT](https://github.com/Danielchen0101/Alpha_lab/blob/c014049715387775b480fd3bf1c20dcb3e8afc7f/LICENSE)，版权署名 Professional Quantitative Trading Platform；用户名称未提供 URL，身份 PENDING，不能假定就是此项目|
|etf-quant|[yansongwel/etf-quant](https://github.com/yansongwel/etf-quant)，owner yansongwel；名称精确匹配候选|b0a86c0467d7d142510ea27bb4beecc6a8c92d7e（main）|[MIT](https://github.com/yansongwel/etf-quant/blob/b0a86c0467d7d142510ea27bb4beecc6a8c92d7e/LICENSE)，版权署名 ETF Quant Contributors；仍需用户 URL 或已有绑定确认|

同名项目存在；AlphaLab 也用于其他研究平台，etf-quant-assistant/research-system 并不是 etf-quant 的同一身份。owner 不等于全部贡献者或真实姓名。MIT 不授权复制第三方市场数据；后续如复制实质代码，必须保留对应版权、LICENSE/NOTICE，并核具体文件附加约束。本批未复制源码。

## 值得吸收的最小内容

1. **轮动项目：先吸收研究合同，不能照搬当前人口/收益标签。** [固定方法论](https://github.com/zhangsensen/etf-rotation-strategy/blob/fb74774af1bcaeffdcbb2b86954274b3b9b93295/frameworks/etf_rotation/ETF_ROTATION_METHODOLOGY.md) 已转为固定 14 ETF、8 组的排序研究。可借鉴冻结人口/方向、共同截面与成熟标签、完整日历后位移、已见年度分离、因果前缀与扰动检验。这些是工程方法，不是本项目已合格的策略。原 docs/OPEN_SOURCE_1430_RESEARCH.md 的迟滞/最短持有引用属于旧平台方向，不能将新主线和旧封版结果混为一体。
2. **etf-quant：作为短公式第二实现参照。** [momentum.py](https://github.com/yansongwel/etf-quant/blob/b0a86c0467d7d142510ea27bb4beecc6a8c92d7e/factors/momentum.py) 的动量为 C(t)/C(t-N)-1；[volatility.py](https://github.com/yansongwel/etf-quant/blob/b0a86c0467d7d142510ea27bb4beecc6a8c92d7e/factors/volatility.py) 为 log-return 滚动样本标准差乘 sqrt(252)。ATR 使用 span EMA；不能替换本项目现有初始化后仍称同版本。它声明无前视不等于本项目 PIT 通过；上游阈值不直接用于仓位或五档。
3. **AlphaLab：暂不吸收算法。** 当前候选是包含回测、组合监控、AI 和 Alpaca execution 的完整平台；本项目不需要整栈或券商执行路径。先确认身份，若继续评估只研究结果/输入 lineage 与回放接口，不能把产品 README 或版本名当作算法质量证据。

## 本地已有实现与差距

- `backend/app/utils/feature_store.py` 已有 return_20d、volatility_20d；`factor_analysis_service.py` 已有局部 Rank IC/ICIR、20日趋势斜率/R²/残差、涨跌日比例、量价相关、60日基准 beta/corr。`add_oss_research_factor_diagnostics` 不进入 production forecast 特征。不要重复新增同义动量、波动、RSI 因子。
- `backend/app/workspace/factor_diagnostics.py` 已有研究矩阵；`backend/tests/test_factor_analysis_service.py` 有研究边界/截后扰动测试入口，本批 NOT_RUN。
- `config/sector_taxonomy.json` 已声明 thincat75/fund-rotation-analyst 的 MIT 适配来源；`sector_timing.py` 将行业 exact/keyword 分类映射为 theme_l1，行业快照只作 corroboration。分类不是 ETF 成份持仓证明；不能用当下映射反写历史归属。`config/research_styles.json` 是 hypothesis_only 风格配置，不是统计验证。
- `sector_rs_vol_gate.py` 的 20日 RS 为严格大于目标的 peer 数+1，percentile=100*(1-(rank-1)/n)，不是 RSI；需冻结 peer 包含自身与否、同值规则和同日人口。当前 `annotate_theme_observation` 缺少 mean_return_20d 时回退 mean_return_5d，仍称 rs_20d，必须在后续授权实现中禁止跨期限代替。
- 同模块 simple_vol_gate 是至少5个有效数的样本标准差、固定0.03阈值；high_vol_percentile 只回显，并未计算分位数。member_returns/returns_sample 可能是成员截面，不足以声称时间序列 realized volatility。首先明确轴、收益单位与窗口；未知保持 unavailable。不得把它称为已验证波动分位门控。

## 推荐下一次有界实现合同

优先修口径和重放证据，不扩展新因子家族。只保留现有20日动量、同日peer RS、真实时间序列波动与行业→ETF证据映射：

- 输入必须包含 ts_code、trade_date、available_at/source_as_of、basis、adjust、source、revision/input_hash；目标日期只消费当时可得数据。14:30 未收盘观测不能顶替 settled 日线特征。
- RS 缺20日值不回退5日；同一 as_of、资格与窗口才进入peer。返回 peer_count、tie_policy、universe_hash、rank、研究版本和不可用原因。
- 波动输入明确为一个ETF逐日收益，按冻结窗口计算；若现有 daily simple-return/年化定义不同于上游 log-return，作为定义差异对账，不强求相等、不静默替换。截面离散度另名。阈值/初始化/门控如改变须升级版本。
- 行业映射返回原行业名、taxonomy版本、exact/keyword匹配方式、ETF匹配来源/有效区间与置信状态。无持仓/跟踪指数证据仅为主题标签，不推断资金流或暴露权重。
- 输出固定 research_only=true、actionable=false、not_calibrated；不改变五档、不加入模型输入、不生成交易任务。全程由Python确定性计算，LLM只解释已存结果。

## 独立验收与接收字段

先写失败复现：20d缺失/5d存在、peer同值与异日、bool/NaN/负价格、窗口不足、截面误作时序；再用同一冻结日历/价格基准的合成及获授权真实样本做本地第二实现对账。保留每日期输出、误差、失败原因、输入和配置哈希；后缀扰动不能改变过去结果，重放不能在dropna后位移交易日。

真实资格另需存量数据 vintage/PIT、上市退市人口、历史分类、复权与现金分红、标签成熟与purge/embargo、冻结参数walk-forward/OOS、依赖/多重试验、基准与成本换手对照。价格公式对账PASS或上游测试数不能替代这些门槛；没有证据不称可靠、calibrated或可执行。

固定SHA接收由父执行者补齐：implementation_sha=PENDING；tree=PENDING；tested_sha=PENDING；commands/results=NOT_RUN（本评估）；artifact_hashes=PENDING；remote_review=PENDING；production_change=NONE。最终提交后接收必须绑定实际SHA/tree和本地运行收据，不填推测的通过结果。
