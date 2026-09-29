# R4C M3B-A2 — 周/月输入身份实施计划

日期：2026-09-30。C2C：`c2c_a1d7` / iteration 66。基线：`f854d6c9db0b774687f226cfb587cc03ddc814c5` / tree `ccab1b644ef9304e5b78ef57c8fd1ff161b480b7`。

## 目标、授权与出口

远端 iteration 65 精确审核 `M3B_A_DECISION=PASS`、`ROUTE_A=RETAIN`、`TECHNICAL_DEFECT_FOUND=false`，并授权 `M3B_A2_GO=true`。A2 把已接受、已结算 D 日线的 R4A 研究输入按现有 `aggregate_bars()` 确定性转换为 W/M `PreparedResearchInput`。不增加第二套行情/复权管线，不改 daily 身份或 M2 的 canonical `input_hash`。

A2 没有运行时消费者，`DEPLOYMENT_DISPOSITION=NOT_DEPLOYABLE_SUBSTAGE`。B/C/M4/主线/生产仍 NO-GO；真实资格 UNKNOWN，runtime disabled，`actionable=false`。仅 A2 远端 PASS 后才可制定 M3B-B 方案。

## 冻结技术合同

1. **唯一来源**：W/M 先以相同 settings 和 as_of 调 `freeze_chan_input(..., interval="D")`。日线 blocked 则上层用同 reason/detail blocked；不重新读取 DailyBar，不读 chart_data，不调用 Provider。
2. **聚合规则**：调用 `backend/app/workspace/candle_periods.py::aggregate_bars()`，映射 W→`1w`、M→`1mo`。周一开始、周期终点和月末 weekday 沿用原函数；时间戳是最后实际观测的 constituent session，不造 Friday/month-end K，不补交易日，不更改假日算法。OHLC 用已有聚合，volume/amount 沿用“所有成分已知才求和”的规则，true zero 不转换。
3. **逻辑序列**：复用 `_logical_series_id(instrument, "W"|"M", price_basis_id, adjustment_version)`。D/W/M 各自隔离，cutoff、成分数量及 input hash 不进 logical ID。
4. **聚合合同与身份版本**：`PERIOD_INPUT_CONTRACT_VERSION="r4c-calendar-period-v1"`，`PERIOD_SOURCE_BAR_ID_VERSION="r4c-period-source-bar-v1"`。Period config 为 `stable_hash({"base_config_id": daily.config_id, "period_input_contract_version": PERIOD_INPUT_CONTRACT_VERSION})`；W/M 可共享 config ID。
5. **每根 period source_bar_id**：稳定 hash 绑定上述版本、instrument、W/M、price_basis_id、adjustment_version、period_start/end、最后 constituent 时间、成分 D `source_bar_ids` 的顺序，以及聚合 OHLCVA。更正一根 D 只改所在 W/M aggregate；同周期追加只改当前 aggregate；下周期追加只增加一根新 aggregate。
6. **revision/hash**：`input_revision_id` 绑定 W/M logical series 与顺序 period source IDs；只能调用 `prepare_research_input()` 生成 input_hash。
7. **时间与结算**：以 M2 UTC-normalized bar timestamp 还原到 Shanghai，再把真实 D settlement timestamp 交给 `aggregate_bars(now=market_as_of)`。period 聚合 timestamp 是最后 observed D timestamp。末聚合 is_partial 为 true 则 settlement=`temporary`，否则 `settled`；这表示日历周期未闭合，不允许 provisional/unsettled D 进入。
8. **lineage**：`FrozenChanInput.constituent_source_bar_ids` 保存 W/M 每根聚合对应的有序 D source IDs。D 返回空 tuple并冻结其现有 IDs。该字段内部可审计，不进入 API。

保持 A2 的实现只在 `backend/app/research/chan_input.py`、`backend/tests/test_chan_m3b_input.py`、审核收据、状态/交接/任务/经验文档及本计划内。默认不改 `candle_periods.py`；只有证明必须抽取纯 helper 才可再改，并须重跑所有 candle/R4A 测试和 full Windows pytest。

## TDD 顺序

- [x] 从固定 515880.SH 两事件夹具，在任何源码更改前输出 D ledger 并冻结测试期望。A2 后须逐字段一致：

```json
{
  "logical_series_id": "af9feaa0fe9554bf9767a90a5656844676564852d03fb75358f08315e1435cab",
  "price_basis_id": "7bfddf99661c4948f4ca2dd7de9ebd37927e4a3e74acd1e3debb7fccb224ed82",
  "source_bar_ids": [
    "5bf1c34f7815fe27271b9289cc5e34f923c68b016b5adbdae51a60250811f2ce",
    "8d3854cb322b4283bef434249f5772d5def286f6f6a1ca5c26b679cf43aa71fe",
    "b4d058a09127ca94ddaafcc22cb8bce252d461159e11eff8905efe5d49c200ed"
  ],
  "input_revision_id": "7851521c6bcbb8a5e72bbcb988989659f5a8e2a19ff405651db77e28778ec339",
  "input_hash": "c73dd49ea9fa361b98cea4c7645733e06fb4752c4d748db0ee97016d61375dc6",
  "config_id": "044ae6adf34067e1c8bdec7f18eab21a7de9c7fb691519f27bf8caabfd293abf",
  "settlement_status": "settled"
}
```
- [x] 新增 RED W/M 测试：周期 OHLCVA/timestamp 等于 aggregate_bars；logical W/M namespace 独立；跨周/月边界以及聚合 bar 顺序正确。
- [x] 新增 RED source ID/revision/config 测试：有序 constituent IDs 参与 period ID；open period 追加只改末 aggregate；new period 只追加；历史修订只改受影响 period；D ledger 逐字段不变。
- [x] 新增 RED partial/settled 测试：周三收盘和月中为 temporary；周五/月底最后 weekday 15:15 后 settled；不添加 provisional D。
- [x] 新增 RED corporate action 与量额测试：effective_through 前后 price-basis namespace 正确；未知量额阻断，true zero 求和为 zero；一根 D 成分允许聚合。
- [x] 冻结 lineage：D 为空 tuple，W/M 一聚合对应一组有序 D source_bar_ids；测试重复调用和来源顺序稳定。
- [x] 实现 W/M 分支：保持 D 主分支原结果 byte-for-byte；blocked 原因安全映射；现有聚合器给结果，M2 验证器构建 PreparedResearchInput。

## 验证与交接

项目 venv 执行 A2 定向、`test_v103_history.py`/calendar/R4A、M2 和 M3 persistence tests。复验 M2 Windows Python 3.12.14/CZSC 1.0.1、Linux 同版本与 R5 Windows/Linux validators。冻结 M2 摘要 `091254d34ddfeeadc85cd0b17e035295bfc32f8a0cebc6776440f10be82aaeac` 和 R5 history digest `d637b4f80c749db48d06dfafe3762216d684ff2827149b4024a3de3f814fc1e9`；collision 0/0/0，弱 ID self-test 必须检出。另跑 Ruff、compileall、Node、scoped secret scan、diff-check。

2026-09-30 verification: focused combined suite 96 collected, 92 passed, 4 environment skips, 0 failures/errors; M2 Win/Linux 25/25; adapter/R5 digests and collision gates unchanged; Ruff/compileall/Node/secret/diff checks passed. Evidence files are listed in the R4C receipt addendum. These results bind the current uncommitted A2 candidate and must be recorded again after commit/push with exact SHA/tree.

若未修改共享 R4A/日历运行时代码，A2 使用上述 focused gate；不得把上一阶段 Windows full suite 当作 A2 测试。如需修改 `candle_periods.py` 或其它共享 runtime 文件，则增加相应 RED/R4A parity 和完整 Windows pytest。

收据须绑定 base/code/test/final SHA/tree 和 GitHub branch/head，含 D before/after ledger、W/M logical/source/revision/config/input identities、每种测试与平台输出、失败历史、`provider_called=0`、`czsc_application_execution=0`、`database_DML=0`。

推送后交同一 ChatGPT Project 审核 A2 技术合同和实现。PASS 才接收下一阶段计划。真实数据 UNKNOWN；不执行 worker/API/UI/生产部署或自动交易。
