# 展示包身份与周末发布运维手册

适用对象：本机（Windows）计算端与云端 ECS 只读展示端的日常运维。目的是让"网站空白"这一类故障能在 5 分钟内定位到唯一原因，而不是逐个猜。

## 1. 架构边界（不可越过）

- 采集、清洗、确定性计算、指标/预测全部在本机完成；产物是**有界展示包**（bundle），签名后 HTTPS 上传。
- 云端 ECS 只做三件事：认证、个人持仓/自选事务、读取展示包渲染页面。云端**不得**运行行情抓取或回测（`SCHEDULER_ENABLED=false` 即为此边界）。
- 展示包有效期 2 小时；过期包仍可显式读取，但必须标记为历史（`is_stale=true` / `historical_identity`）。
- `actionable=false`、资格 `UNKNOWN`、`not_calibrated` 不因任何运维动作改变。

## 2. 展示包身份 ≠ 应用版本（故意解耦）

云端 api 用环境变量 `SHADOW_SYNC_CODE_SHA` / `SHADOW_SYNC_CONFIG_HASH` 与每个包 manifest 里的 `code_sha` / `config_hash` 比对。不匹配时默认读取返回空（fail-closed），页面显示"尚无可消费批次"。

解耦是必要的：只改网站代码的发布不能把已有包作废。但解耦必须靠登记表维持秩序：

- 登记表：`config/bundle_identity_registry.json`（当前批准的生产者身份，按批准日期排序，最后一条即"当前生产者"）。
- 部署前门禁：

```bash
python scripts/check_bundle_identity.py \
  --code-sha "$SHADOW_SYNC_CODE_SHA" --config-hash "$SHADOW_SYNC_CONFIG_HASH"
```

退出码 0 = 已登记生产者；1 = 未登记（先修身份，不要把空网站当数据故障）。

### 推进生产者身份（只有这一条路）

1. 在**干净工作树**里确认真实交易日取得 34/34 合格日线（全量 run 成功，报价诚实降级不算）。
2. 同一工作树导出并上传，服务器回执 `accepted`，默认读取 `total=34`。
3. 更新登记表：新增条目（新 `code_sha`/`config_hash`/`approved_at`），旧条目用 `superseded` 记录。
4. 发布候选同时改 `SHADOW_SYNC_CODE_SHA`/`CONFIG_HASH`，跑上面的门禁。
5. 切换后复验默认读取 `total=34, is_stale=false`；失败立即 `rollback.sh`。

禁止：把包里读到的 SHA 直接抄进环境变量；跳过第 1 步；只为"让页面有数"而放宽身份比对。

## 3. 周末 / 节假日发布（board-only 逃生门）

非交易日没有合法全量出包路径：`_closed_research_session` 要求当天是已验证交易日，普通全量的 `refresh_quotes` 会以 `partial` 拦截必需任务。周末网站因此会在包过期后变空——这是设计内的诚实空态。

需要周末延长展示时，用合同内的 board-only 路径（只从本机已存行重建决策板，不采集行情）：

```bash
"<venv>/Scripts/python.exe" "<worktree>/scripts/run_local_compute.py" run \
  --root <数据根> --profile live --provider public_composite \
  --config <数据根>/config/live.json \
  --expected-sha <工作树 HEAD> \
  --private-research --skip-trade-day-check --board-only
```

- 先核对 `<worktree>` 的 `git rev-parse HEAD` 等于登记表当前 `code_sha`，否则中止。
- 它**不产生新行情**，只是把已存结果重新发布并延长有效期（2 小时）。
- 每个交易日 11:40 起的正常槽会自动接管，无需人工。

### 退出码必须看进程，不看管道

`run_local_compute.py` 失败时返回非零，并在 stdout 末行打印 `{"exit_code": N, "status": "failed", ...}`。

```bash
python ... run ... | tee run.log
echo "${PIPESTATUS[0]}"     # bash
```

或直接检查日志最后一行是否含 `"status": "failed"`。**不要**只看 `echo $?` 或尾部 grep 结果。

## 4. 网站空白的排障顺序

1. **身份**：跑 `scripts/check_bundle_identity.py`；未登记 → 身份问题，不是数据问题。
2. **有没有包**：容器内 `ls -lt /app/.local/display-cadence-*/`，看 `latest.json` 的 `sequence`/`expires_at`。
3. **过期没有**：`expires_at` 已过 → 诚实空态；跑第 3 节流程或等下一个交易日槽。
4. **覆盖**：`total` 是否 34；某代码 404 `local_display_instrument_not_published` = 该标的不在本批 universe。
5. **报价新鲜度**：`status=stale` 表示源时间超出 600 秒观测窗口或整包过期；`is_realtime=false` 是正常状态，不是故障。

## 5. 明确禁止

- 在 ECS 上跑抓取/回测/重算，或打开 `SCHEDULER_ENABLED` 让云端回填研究数据。
- 手改生产数据库、`latest.json` 或包文件。
- 用成本价、旧报价或 Mock 数据填"缺失"的展示值。
- 超过 2 小时有效期后仍把包内容描述为当前数据。
