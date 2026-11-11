# R0/R1/R2 外层系数离线回放候选（待审）

本次只增加研究入口。无 API 注册、定时任务、Provider 网络调用、交易接口、生产配置修改或历史补传。

## 查重与复用

- 2026-11-11 读取远端 main：`1ec6f38281598d76f6208c96c85704ff9aab8a82`；远端现有分支与开放 PR #67/#53 已检查。PR67 的通用 PIT/OOS、事件回放组件已在此 main，不另复制或覆盖。
- 本候选直接调用 `compute_structure_shadow` 和 `apply_structure_decision`，并锁定两份源码的 SHA256。冻结 soft_c 40:60、置信门槛 .45、阈值 .30、中性带 .12 和 ATR 档缩放；不直接重写或近似舍入。
- 只比较结构决策层 R0=0、R1=.3125、R2=.4167。不改 Board/MACD、factor、family、基础五档规则及 `strategy.json`。
- 时间切分复用 `app.utils.time_split`。next-open 入场后持有 20 个交易日的退出在信号后第21个交易日，跨窗清除因此用21，而非20。
- `STATUS.md` / `HANDOFF.md` 顶部有历史漂移，不能据其断言当前部署。本文源码基线不是生产验收。
- 本候选不启动用户本机 Agent、不新建 ChatGPT Work/Codex 执行会话、不用 Cursor 云端额度。

## 已实现

1. 输入冻结池、明确交易日历、原始价格、带可用时间的基础档位/结构数据；拒绝重复键、错误代码/配置身份、未知动量复权口径和非有限数值。
2. 每个期限分别形成 ETF × 信号日共同机会集。结构缺失回退原档；数据异常对所有策略禁止新风险；5日动量用截至当日可用的同复权口径6个收盘值，严格按日历取5个交易日。R0同时是基础五档和全结构消融对照。
3. **因果信号资格与事后标签资格分开**。远期缺失/无效/未成熟仅共同排除标签统计，不反向取消先前交易或缩短回放终点。交易日历、预声明窗口、相位、期限决定固定终点；完整终点未成熟时该实验返回空，不填0。
4. 五档目标为0/0/.25/.5/1，再除冻结池数量。100万元，100份整手（研究假设），不加杠杆，下一交易日开盘执行，5日和20日独立实验。卖出先行，现金不足时按比例缩买，不优待代码排序；完全成交、部分成交、未成交分别记录。
5. 开盘快照无效或快照成交量为0不成交；已有头寸保留。每次交易佣金万二、最低5元、单边滑点万五；终止清算同样计费；三项同时翻倍作压力测试。税费假设0，非券商已核费用。
6. 日净值、现金、份额、费用、滑点、换手、回撤、暴露、成交率、末期未平仓，以及缺失估值均留账。开盘快照需在当日09:30前可知，收盘价需在当日16:00日结前可知，且均不得晚于输入 `as_of`；陈旧估值保留上次已知价并标 `indicative_stale`，不生成配对置信区间。
7. 每个策略使用相同因果信号机会、同一交易/费用约束。always_long是“共同资格门控的恒定做多基准”，不是不受门控的买入持有。5日实验考察5/10日块，20日用20日块，联合抽取日期，固定种子61111。R1−R0/R2−R0的两主比较以Bonferroni修正，另四个与always-long/动量基线比较独立成一族。少于4个完整块不出区间，少于20块标低检验力。
8. 枚举所有再平衡相位，仅保留相位0完整账本，其余输出汇总，不能据其中最佳相位选参。
9. 已看到的2026-11-10及以前永不标最终样本外；`seen_through`只能向后扩。120日仅为观察建议，非功效保证。输入的冻结时间和收据引用不能自证未见数据，`final_oos_validated=false`始终保持。
10. 输出策略/输入/研究池/日历/公式/回放代码哈希、逐行排除原因与档位、账本、净值和结果文件校验和。全程不修改输入，输出目录必须新建。

## 明确未完成与不可宣称

- 没有取得本次真实历史原始开盘、可信的基础五档时点记录或公司行动账本，没有运行真实回测，不能报真实胜率、收益或最优系数。
- 当前只支持**有证据覆盖且事件列表为空**的公司行动区间。账本缺失、范围不全，或存在任何拆分/分红等事件，都仅产出信号层完整性报告，不猜测事件处理或宣称净收益。需后续另行实现/验证分红支付、拆分及税处理。
- 基础档位需来自既有可信时点产物；本模块不从今日数据重建历史基础规则树，也不证明输入收据真实。
- 原始价与证据齐备时仍仅为条件模拟：涨跌停队列、盘口、价格冲击与交易单元的历史差异未被证明，不是可执行绩效。100份整手与0税费只是明确假设。
- 历史成分、退市与主题 PIT 未验证，只能称冻结池研究，不能声称无存续偏差。主题计数是调用方提供的未验证标签。
- 时间切分输出清除边界；本工具不自动训练/调参。无足够开发数据时不生成4折，不把“有计划”说成真实走完walk-forward。
- MA/MACD/动量/道氏、KDJ/RSI相关性及分因子消融缺独立PIT特征输入，未实施这部分，报告明确列出。主比较仅研究外层系数，不能暗中重选soft_c。
- 至少20个改档决策日、双倍成本仍增益、回撤恶化≤2个百分点等是待评审门槛，本候选不自动晋升。`actionable=false`、`not_calibrated`、`promotion_allowed=false`。

## 输入与运行

入口：`python scripts/replay_structure_weights.py --input /isolated/data.json --output /isolated/new-run`

只读输入JSON（UTF-8，≤128MiB）。`config_sha256` 是基线 `config/strategy.json` **原始文件字节 SHA256**，不是生产的CONFIG_HASH。本基线值：`50b48ab7fb71c1a2650ab661b8377a8f865190e002a882911a0b034da2d8d427`。

顶层字段：

- `schema_version`: `structure-weight-input-v1`。
- `universe`: 唯一6位ETF代码列表，也接受`.SH/.SZ`后缀，必须与各行一致。
- `calendar`: 已核实、严格升序的交易日ISO日期数组，含至少5个预热日和退出所需后续交易日。不自动把自然日补成交易日。
- `signal_start` / `signal_end`: 预先声明研究信号窗口。窗口内缺失行将显式计入共同排除。
- `as_of`: 数据实际可用截止，必须有时区；`frozen_at`: 规格冻结时间，必须有时区；`seen_through`: 已看资料截止，最低2026-11-10。
- `source_manifest`: `code_sha`必须为上面的完整基线；`config_sha256`为上面文件哈希；`signal_definition=base_grade_before_structure`；`momentum_adjustment=consistent_total_return`；组合模拟另需`price_adjustment=raw`、`raw_price_evidence_ref`、`signal_pit_evidence_ref`与`execution_snapshot_evidence_ref`。引用必须来自实际记录，禁止假造。
- `signals`: 每行`date/code/base_grade/decision_at/available_at/inputs_as_of/structure_v1`。结构块沿用已有字段`wyckoff_score/wyckoff_confidence/dow_score/dow_confidence/atr_risk_bucket`。基础档位不应已含结构调整，否则会重复计入。可选`theme`仅供未验证分层计数。
- `bars`: 每行`date/code/open/close/volume/momentum_close/available_at`，另有独立`open_available_at/open_volume`开盘成交快照和可选`close_available_at`（缺省回退日线available_at）。open/close为原始价；momentum_close是跨日一致的总回报复权研究序列；open_volume>0且open_available_at<=当日09:30才可模拟成交，不能使用收盘后整日volume倒推开盘状态。收盘估值需close_available_at<=当日16:00，否则保留已有估值并标陈旧。所有时间为真实可用时间，不得用抓取日代替历史可用时点。
- `corporate_actions`: `coverage_start/coverage_end/evidence_ref/events`。范围覆盖完整输入日历；只有确证无事件的空数组才进入本版组合模拟，禁止用空数组代替未知。

退出码0：生成条件模拟（不是研究通过）；2：仅信号层，报告含组合阻塞原因；1：身份/格式/文件错误或输出路径已存在。使用者应读取`status`和每项限制，而非只看退出码。

输出：`report.json`（完整）、`manifest.json`、`opportunities.jsonl`、每期限/成本/策略的`trades.jsonl`和`daily_nav.jsonl`、`checksums.json`。生成失败留`INCOMPLETE`标记；不得作为完整回执。

## 测试与回滚

依赖最小测试：`PYTHONPATH=backend python -m unittest discover -s backend/tests -p test_structure_weight_replay.py -v`。

项目pytest会自动收集同一测试文件。合成夹具仅测试工程逻辑，不是市场数据，不能用于资格晋升。详见本次交付测试收据。

回滚：本版本不接入生产，停止运行离线CLI即可；审查分支若放弃，仅撤回本次新增文件，保留已生成研究/失败证据。无需数据库迁移、生产配置反转、包重传或删除生产数据。集成前先核最新main与两个公式源哈希；若漂移，明确重新评审，不能修改哈希绕过冻结。

补充执行限制：`open_volume` 仅作为>0的开盘活动门控，不是可成交容量模型；本版不把订单数量限制在开盘成交量内，也未模拟排队。即使快照时间字段齐备，所有结果仍标 `execution_pit_verified=false`，不得将条件模拟称为真实可执行回报。
