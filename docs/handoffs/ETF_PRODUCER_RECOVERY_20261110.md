# ETF 本机生产恢复与结构链修复交接（2026-11-10）

> 范围：修复 2026-11-09 本机停产与 structure_v1 未进入展示包两条链。
> 云端已完成代码修复与测试（分支 `muse/etf-structure-chain-fix-20261110`）；
> 本机执行部分（Windows 任务、补算、身份登记、ECS 期望值切换）必须在本机
> 按本文顺序完成，并以真实产物验收。健康检查 200 不作为业务验收证据。

## 1. 已确认根因（2026-11-10 云端复核）

### 1.1 本机停产
- Windows 任务 `ETF-Local-Live-Compute` 的 WorkingDirectory 指向已被删除的
  临时工作树 `C:\Users\Admin\.codex\worktrees\etf-live-v113-a0d52e4\...`，
  2026-11-09 18:20 运行返回 `0x8007010b`（ERROR_DIRECTORY）。
- 仓库既有 `scripts/migrate_local_cadence_task.ps1` 无法处理该情形：它要求
  旧树仍存在且干净（对旧 WorkingDirectory 执行 Assert-CleanSource）。
- 现存稳定检出 `E:\project\ETF-Fund-Analysis` 审计时 HEAD 为 `3ce3a743`，
  与任务仍 pin 的 `--expected-sha a0d52e44...` 不匹配，不能只改路径。

### 1.2 structure_v1 未进入展示包（双重剥离）
决策板 `DecisionBoardService` 已把 `structure_v1`（威科夫/道氏/ATR）与
`structure_shadow` 算入 board 行，但生产者序列化链上两处白名单把它们剥掉：
1. `backend/app/workspace/read_model.py` 的 `compact_row` 键列表；
2. `backend/app/workspace/local_compute.py` 的 `ROW_FIELDS_V2`。

消费者（`local_display_read`）逐字透传 bundle 行，前端主表也早已按
`row.structure_v1` 渲染三列——缺的只是包里没有字段。本次修复已补齐两处
白名单，前端三列标题改为「威科夫结构 / 道氏趋势 / ATR 波动风险」，ATR 列
附带 ATR14 与 ATR 百分比（`atr_pct` 为小数，展示时 ×100）。旧包无字段时
仍显示「—」，不回填中性/低风险。结构加权（structure_decision，权重
0.4167）为既有已批准实现，本次未改动。

### 1.3 部署背景复核（2026-11-10 01:16–01:20 云端 SSH 全量实测，更正版）
- ECS 实际运行的是 **`etf-deploy-0e2f888` 栈**（api/worker/scheduler，
  healthy，restarts=0，启动于 2026-11-09 22:18 CST，api 占用
  127.0.0.1:8080）——所有者的部署报告（consumer `0e2f888`、镜像
  `china-fund-decision:deploy-0e2f888`）**属实**。旧 e086e83 仅剩镜像，
  容器已不在运行。
- 运行中 api 的消费者期望仍为 producer `a0d52e44...` /
  `a12c6ea1...`（SHADOW_SYNC_CODE_SHA / SHADOW_SYNC_CONFIG_HASH 实测），
  producer/consumer 解耦成立；网站展示的仍是 11-06 的旧包。
- 仍不可核实的两点：分支 `codex/sector-drawer-v1-20261108` 不在
  GitHub 远端分支列表中（muse-vm 令牌可见 26 个分支，无此分支），
  无法对 0e2f888 的代码做 diff 审查；`/opt/china-fund-decision/` 对
  claude-ops 无读权限，部署目录名无法从云端确认。
- ECS 磁盘已用 87%（2026-11-08 为 81%），清理需所有者另行授权，
  本文不处理。
- 更正说明：本节初稿曾依据一次不完整的局部观察误记为「0e2f888 未
  部署、仍运行 e086e83、磁盘 89%」，已于 01:16 以全量容器/镜像列表
  复核后更正；结论以本版为准。

## 2. 本机执行顺序（Jovi 本机，PowerShell 管理员）

前置：把 `E:\project\ETF-Fund-Analysis` 更新到本修复分支最终提交（记为
`<FIX_SHA>`，以推送后的远端分支 tip 为准），工作区保持干净
（`git status --porcelain backend scripts config frontend pyproject.toml`
为空）。不要使用任何 `.codex\worktrees` 临时目录作为生产目录。

### 步骤 A：备份（一致性要求）
1. 导出失效任务 XML 留存：`Export-ScheduledTask -TaskName ETF-Local-Live-Compute`
   （恢复脚本在 -Apply 时也会做不可变备份，此处可作双保险）。
2. SQLite 一致性备份（禁止对运行中数据库裸拷贝）：用 Python sqlite3
   backup API 对 `F:\ETF_Data\ETF-Fund-Analysis\db\research.sqlite3` 做
   在线备份，并对备份执行 `PRAGMA quick_check`，记录 sha256 与字节数。

### 步骤 B：恢复计划任务（新脚本，先预览后执行）
```powershell
cd E:\project\ETF-Fund-Analysis
# 预览（不修改任何东西）：核对输出中的 dead tree、新 action、以及
# “Tasks still referencing the dead tree” 清单（逐星/Reconcile 等其他任务
# 若也在列，只报告、不要顺手开启或修改）
powershell -File scripts\recover_local_compute_task.ps1 `
  -ExpectedSha <FIX_SHA> `
  -Workspace "E:\project\ETF-Fund-Analysis" `
  -Python "E:\project\ETF-Fund-Analysis\.venv\Scripts\python.exe" `
  -LocalRoot "F:\ETF_Data\ETF-Fund-Analysis" `
  -Config "F:\ETF_Data\ETF-Fund-Analysis\config\live.json" `
  -BackupDirectory "F:\ETF_Data\ETF-Fund-Analysis\backups"
# 确认预览无误后加 -Apply 执行：脚本会先把原任务 XML 不可变备份
# （UTF16LE + sha256 旁车），仅替换 action 的树路径与 --expected-sha，
# Triggers/Settings/Principals 逐节校验不变，恢复后的任务为 DISABLED。
```

### 步骤 C：受控首跑（任务 Ready/Disabled 不等于成功）
```powershell
Start-ScheduledTask -TaskName ETF-Local-Live-Compute
# 等待结束后必须同时满足：
(Get-ScheduledTaskInfo -TaskName ETF-Local-Live-Compute).LastTaskResult  # == 0
# 且 F:\ETF_Data\ETF-Fund-Analysis\outbox 出现新 bundle/receipt，
# state\schedule.sqlite3 出现当日 slots 记录。
Enable-ScheduledTask -TaskName ETF-Local-Live-Compute   # 验收通过后才启用
```

### 步骤 D：补算 2026-11-09（收盘后补算，不伪造盘中快照）
任务恢复后，用收盘研究模式补算 11-09（该模式只用已验证收盘会话，
不会把收盘价标成 11:40/14:30/14:45 实时报价）：
```powershell
E:\project\ETF-Fund-Analysis\.venv\Scripts\python.exe `
  E:\project\ETF-Fund-Analysis\scripts\run_local_compute.py run `
  --root "F:\ETF_Data\ETF-Fund-Analysis" --profile live `
  --provider public_composite `
  --config "F:\ETF_Data\ETF-Fund-Analysis\config\live.json" `
  --expected-sha <FIX_SHA> --private-research --closed-session-research
```
验收口径：34 只标的逐项列覆盖（缺失必须列代码与原因）；`daily_bars`
最新交易日为 2026-11-09 且 34/34；新 bundle 的 overview 行含
`structure_v1`（含 wyckoff_phase/dow_phase/atr14/atr_pct/atr_risk_bucket/
as_of）；预测五期限 1/3/7/20/60 齐全且生成日/基础数据日为 11-09 口径，
不得复制 11-06 结果改日期。

### 步骤 E：登记新生产者身份并切换 ECS 期望（同一变更窗口）
新代码产出的 bundle 身份将变为 `<FIX_SHA>` + 新 `config_hash`。新
`config_hash` 以**步骤 D 产物 bundle 的 manifest 为准**直接读取
（`manifest.code_sha` / `manifest.config_hash`）：它由生产者在 live
配置下用 `stable_hash(settings.load_strategy())` 计算，`load_strategy`
会注入运行时设置，脱离生产者环境在别处算出的值不作数（例如云端以
默认设置计算得到的是另一个值）。登记纪律按仓库注册表注释：不得在
没有新鲜 34/34 合格计算的情况下把 bundle 的 SHA 抄进消费者期望——
步骤 D 的合格补算正是该证据。
1. 先在本机完成一次 34/34 合格计算（步骤 D 的产物即证据），
2. 再向 `config/bundle_identity_registry.json` 追加新身份条目
   （code_sha=<FIX_SHA>、config_hash=步骤 D bundle manifest 的值、
   approved_at=当日、approved_scope 注明结构链修复与 34/34 证据），
   单独提交；
3. 同窗口更新 ECS 消费者环境 `SHADOW_SYNC_CODE_SHA` /
   `SHADOW_SYNC_CONFIG_HASH` 为新身份并重启 ETF api/worker；
4. 用 `python scripts/check_bundle_identity.py --code-sha <FIX_SHA>
   --config-hash <NEW_HASH>` 验证登记通过；
5. 上传步骤 D 的 bundle 后，核对服务器 accepted 回执（bundle_id /
   sequence / producer 身份），并登录网站确认：主表三列有真实值、
   数据日期为 2026-11-09、预测五期限可切换。截图留存（脱敏）。

回滚：ECS 期望值改回 `a0d52e44... / a12c6ea1...` 并重启 api/worker 即
恢复旧身份消费；本机任务可用备份 XML 重新注册恢复（恢复脚本失败时
自动回滚并校验）。旧容器/镜像/备份一律保留，不做全局 Docker 清理。

## 3. 云端已验证（本分支）
- 新增失败测试先行复现：投影剥离、列标题/渲染契约在修复前均失败，
  修复后通过；目标测试集 84 项通过，含五期限 reader 透传与预测选择、
  compact_row 空值契约、ATR 单位（小数）与 atr_pct_fixed_v1 边界
  （既有 test_structure_v1 覆盖）。
- PowerShell 语法解析测试在本机/Windows CI 执行（云端 VM 无 PowerShell，
  合同测试以 skip 记录，不冒充已运行）。

## 4. 未完成 / 需本机或所有者确认
- [ ] 步骤 A–E 的本机执行与 11-09 真实补算、上传 accepted 回执。
- [ ] 登录后网站截图验收（三列表头+真实值+11-09 日期；五期限切换）。
- [ ] 其他引用已删工作树的任务（以恢复脚本预览清单为准）逐项处置，
      禁用的不要擅自开启。
- [ ] 本修复分支合入 main 与生产部署（沿用既有部署流程与备份要求）。
- [ ] ECS 磁盘 89% 清理授权（独立事项）。
