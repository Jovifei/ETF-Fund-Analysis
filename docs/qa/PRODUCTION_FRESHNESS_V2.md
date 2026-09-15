# 生产数据证据合同 v2（QA-R02）

本页是原 2026-09-15 Gate 3 标准的明确补充，不覆盖旧报告。
原 gate 存在三类反例：未知计数被 `or 0` 吞掉，任何非空指标版本都算合格，
九小时以前的报价仍可通过 require-realtime。旧四条测试的正例包含最后一种问题。
已保留 RED 记录；改正正例的时间与证据、增加负例，而不是删掉失败断言。

## 工具语义

`scripts/production_data_gate.py` 是无数据库/无 Provider 的离线证据校验器。
它只验证收到的脱敏证据，不证明外部证据本身真实；单位、复权、源资质、PIT/OOS
仍需独立对账及批准。任何结果 `qualification_granted=false`、`actionable=false`、
`deployment_approved=false`。`status=pass` / `checks_passed=true` 只代表这份证据
通过列出的检查，不是完整 Gate 0–7 放行。

退出 0：本份证据检查通过。退出 3：报告已成功写出，但存在数据/缺证阻断。
退出 2：输入格式、重复键、文件、大小或输出错误。输出必须为新文件；不覆盖旧
收据、不跟随 symlink/junction，不读取账户/凭据；Windows 目录 ACL 由接收者验证。

## 生产只读采集者必须提供的字段

- `schema_version=production-freshness-v2`；`captured_at` 有时区，距校验不超过15分钟。
- `source_tree`：实际运行源码树；不是 APP_VERSION，不是另一个本地分支。
- `target_trade_date`、`calendar_verified`：由同一交易日历核验。日期不得非法/未来；上海15:15前不能把当日日线称为已结算。
- `expected_codes`：独立读取实际启用 ETF/LOF 集合；1–200 个唯一规范代码。
  `items` 必须与该集合完全相等；不能用 items 自己反推 expected_codes 掩盖漏项。
- `expected_versions`：从实际运行策略取得 `indicator`、`forecast`、`feature_schema`、
  `config_hash`，不能从待检查快照反抄它们。
- `decision`：target_trade_date、generated_at、config_hash、input_dates_verified；
  最后一个字段必须经过快照输入链路的真实核对。
- 每个 item：ts_code、daily_latest、daily_rows、missing_volume、missing_amount，
  计数必须是非负整数；缺失/布尔/负数/字符串不视为零。
- 每个 item：ohlc_valid、price_basis_verified、units_verified、history_blockers；
  必须由只读历史审核/来源对账取得。不得手动填 true 或置空 blocker。
- 指标：indicator_latest、indicator_version、indicator_config_hash、
  indicator_feature_schema、indicator_input_hash_verified。最后一项要按现有
  完整输入/面板 hash 合同核验，不能直接拿 local-history hash 比较 panel hash。
- 预测：forecast_latest、forecast_horizons 和 forecasts 数组。数组恰为 1/3/5/10
  四期；逐期提供 horizon、as_of_date、model_version、config_hash、feature_schema、
  input_hash_verified、values_valid。只写“4条”不够；空数值、旧配置不得通过。
- 报价：quote_latest（源时间，不是 fetched_at）、quote_realtime、quote_timestamp_verified。
  require-realtime 还要求同一上海自然日、无未来时间、源时间年龄 <= 8分钟。
  研究模式允许标注陈旧/未验证的报价，但仍不授予资格。

字段示例见 `backend/tests/fixtures/production_freshness_v2.json`，它是虚构测试，
不能当生产收据或复制其标志。旧 freshness JSON 缺字段时会明确 fail / 退出3；
禁止用转换脚本自动补 true/零。这不意味着新增了在线采集器，本阶段未开发该功能。

## 执行

在授权的只读诊断已产出新鲜 v2 证据之后，执行：

```text
python scripts/production_data_gate.py --input <new-private-freshness.json> --output <new-private-gate.json> --require-realtime
```

固定基线旧历史收据依然保留，只能用于当时事实回溯，不能冒充今天的数据验证。
工具会将原始输入 SHA-256 写入输出，保留命令、退出码和文件 hash；不要把私人
生产 JSON 加到 Git。真实数据继续 BLOCKED_DATA 时不得部署。
