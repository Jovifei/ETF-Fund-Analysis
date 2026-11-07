# 2026-11-06 策略与生产落地闭环计划

目标：在不启用自动交易、不放宽 actionable/calibration 门禁的前提下，完成新策略的同口径验证、真实 PIT 数据准入、shadow 审计和生产自然链路验收。

## 阶段 A：策略统一合同

- [ ] 明确运行时 strategy_engine、SignalV05、RotationBacktestV05 的共同版本/输入/输出合同
- [ ] 让回测逐笔账本复用运行时策略评分、动作状态、目标仓位和迟滞语义
- [ ] 增加 exact replay 回归测试与失败样例
- [ ] 运行策略相关测试、compileall、Node 检查，提交独立阶段

## 阶段 B：真实 PIT/OOS 验证

- [ ] 核查 Provider Adapter、许可、5m/15m OHLCV/amount、source timestamp、新闻发布时间和第一条可成交价
- [ ] 建立 14:30 cutoff、horizon-aware purge、pristine holdout 和版本冻结报告
- [ ] 将 T+1、费用、滑点、最小单位、涨跌停、停牌、LOF/QDII 溢价、组合约束纳入事件回测
- [ ] 保持资格门禁；只有证据完整才生成候选封版报告

## 阶段 C：Shadow 与运营验收

- [ ] 每个交易日 14:30 生成不可变 shadow 快照，建议至少 20 个交易日
- [ ] 验收两个真实交易日自然槽、7–14 日稳定性、快槽时效、正常登录和手机
- [ ] 完成 AI/SMTP 配置后做真实投递和缺席通知验证；未配置前保持停用
- [ ] 对齐 STATUS/HANDOFF/CHANGELOG 与实际 HEAD、生产者和证据

## 保护边界

- 不连接券商、不自动下单、不直写生产数据库、不删除受保护数据和回滚资产。
- Mock、stale、partial、未校准、未完成 walk-forward 的结果继续 actionable=false。
- 每阶段必须有失败证据、测试收据和可回滚提交。
