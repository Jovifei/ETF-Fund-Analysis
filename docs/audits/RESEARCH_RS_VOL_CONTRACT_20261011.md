# RS/波动研究合同最小修复 — 2026-10-11

状态：LOCAL_TARGETED_PASS / REAL_DATA_QUALIFICATION_NOT_RUN。实现与测试尚未提交，由父执行者绑定最终 SHA/tree 后远端独立复审。

## 合同变化

`backend/app/utils/sector_rs_vol_gate.py` 的独立研究合同升级为 `sector-rs-vol-research-v2`，不是 canonical 策略或预测版本变化。

- rs_20d 仅消费 mean_return_20d；缺失不借用 mean_return_5d。原严格大于目标的 peer 排名与百分位数数学保持。
- annotate 波动只消费 `returns_axis="daily_time_series"` 加 `daily_returns` 列表。旧 member_returns/returns_sample 和未知轴不用于 realized volatility；未知轴输出 unavailable / daily_time_series_axis_required。
- simple_vol_gate 明确输入为日频 decimal 收益时序；沿用有效样本 >=5、样本标准差（ddof=1）、非年化固定0.03阈值。无分位门控。移除从未参与计算的 high_vol_percentile 参数，调用者传入时 Python TypeError 明确拒绝，不再回显伪配置。
- grade、canonical 评分、forecast 特征、strategy.json 不变；输出仍 research_only=true、actionable=false。模块入口搜索仅找到现有测试，没有自动激活业务运行路径。

## 本地证据

执行 cwd：`E:\project\ETF-Fund-Analysis\.local\local-execution-20261011`。
执行解释器：`E:\project\ETF-Fund-Analysis\.local\demo-afdf6c2-20261009\.venv\Scripts\python.exe`（已有312环境，未安装依赖）。

1. 改源码前：`-m pytest -q backend/tests/test_sector_rs_vol_gate.py`，退出1，原4例通过、新6例失败。复现5d冒20d、截面/未知轴输入误用、显式daily输入未消费及percentile参数未拒绝。
2. 改源码后首次：相同命令退出0，10例通过。
3. 加真实固定数学值/无daily字段/无效值不计样本边界后：相同命令退出0，12例通过。
4. `-m compileall -q backend/app/utils/sector_rs_vol_gate.py` 退出0。

测试出现现有 entities.py:645 SQLAlchemy registry 命名警告；无测试失败。本批未运行全量pytest、生产测试、PIT/OOS或真实样本回放。父执行者统一全量检查与收据，不将本定向PASS当作全系统或算法资格PASS。

## 资格局限

显式轴是输入合同声明，不是交易日连续性、available_at、历史revision或单位已经核实。direct helper 的调用者仍负责日频时序；过滤无效值会减少样本，不证明缺失日期可忽略。后续真实回放须冻结窗口、日历、peer人口/同值策略、价格基准和taxonomy有效期。未完成walk-forward/OOS、输入vintage与因果前缀验证，不晋升可靠性/校准/交易资格。
