# 剩余三大项执行计划（S8 数据资格 / 云盘保留策略 / 7–14 日 soak）

制定：2026-10-25，基于 v1.0.7（`dcffa8e`，镜像 `d85d40cd`）发布后的现状。执行人：本地 Agent（主），Jovi 决策点单列。本计划是验收合同：每阶段有明确产出与判据，不以"计划存在"代替交付。

**三项并行推进**：soak 是观察性工作（自动化采集+人工检查点）；云盘是运维治理（先策略后授权清理）；S8 是研究工程主线。互不阻塞。

## 已核实的现状事实（2026-10-25）

- soak 工具链已存在：`scripts/observe_local_cadence.py`（SSH 只读采集）、`scripts/capture_local_stability.py`（离线评估）、`local_stability.assess_session`（内置两个真实交易日判据）。旧 `ETF-Local-Cadence-Observe-*` 任务为 disabled 且绑定旧 SHA/旧 image-id，不可直接复用。
- 云盘（ECS `/` 40G，已用 27G，剩 12G）：`backups/` 1.2G（10-02 的 326M `sql.gz` + 10-25 两次发布各 424M `pg_dump`，**每次发布 +424M**）；Docker 镜像 6.19G 其中 **5.32G 可回收**（85 个镜像仅 16 个活跃）；`release-local-live-c6ce85c/` 旧 context 423M。
- S8-F0：`docs/planning/S8_F0_DATA_FEASIBILITY_SPIKE.md`（F0-01~F0-10 十步规范）与 `docs/audits/S8_F0_SOURCE_MATRIX_20261002.md`（v5，2026-10-05）已就绪，但矩阵状态 **DOCS_ONLY**——Tushare/FTShare/AKShare/Sina 四源均 UNKNOWN，无任何真实接口探测。`backend/app/services/pit_oos_harness.py` 已有 PIT/泄漏/walk-forward gate 骨架；`scripts/build_1430_point_in_time_dataset.py` 已有。
- 手机实测（Jovi 侧）结论尚未回收；子 agent 通道（GLM-5.3-Flash）不可用，恢复后可并行派发调查任务。

## 阶段 0：soak 启动（10-26 周一，收盘后约 1 小时）

前提：v1.0.7 已上线，16:40/17:40 新槽当日首跑。

| # | 操作 | 产出/判据 |
|---|---|---|
| 0.1 | 22:00 前核对周一全部 12 个槽的台账状态（重点 16:40/17:40 首跑：是否 DELIVERED；若 FAILED 看 refresh_bars 完成度） | 台账截图/查询结果入收据；当晚结算是否落地 |
| 0.2 | 用 `observe_local_cadence.py`（更新 `--expected-source-sha dcffa8e…`/新 image-id 参数后）做第一次 capture | 第一份观察 JSON |
| 0.3 | 固化 soak 基线：三容器 RestartCount=0、镜像 digest、df 数值、备份清单、同步域字节数 | `docs/audits/SOAK_BASELINE_20261026.md` |
| 0.4 | 注册新的每日观察任务（18:30 触发，替代旧 disabled 任务；或前 3 天手动跑） | 任务 Ready 且首日成功 |

**Gate**：0.1 若新槽仍 FAILED（数据源 17:40 还不出齐），记录完成度曲线并评估是否加 20:40 槽（小幅代码改动，走同一 RED→GREEN 流程）。

## 阶段 A：7–14 日 soak（10-26 → 11-06 中期 / 11-13 收官）

每日自动采集（已有工具，无新开发）：slot 台账交付率与失败原因、16:40/17:40 结算落地时间、容器重启/OOM、`/api/health`、磁盘与备份、同步域字节数、公网 health。

人工检查点（本地 Agent 执行，Jovi 可随时看）：
- **Day 2（约 10-28）**：`assess_session` 两真实交易日判定（S8 之外的关键运营门槛）；失败则修复并把 soak 窗口重新起算（诚实规则，不累计带伤窗口）。
- **Day 7（约 11-02）**：中期报告（`docs/audits/SOAK_DAY7_*.md`）+ Hub 事件。
- **Day 14（约 11-13）**：收官报告 + S9-U05/U06/U07 判定。

**通过标准（冻结）**：① 无未解释的容器重启/OOM；② 全部槽按合同 DELIVERED 或诚实 FAILED 带原因（FAILED 率无恶化趋势）；③ 磁盘增长符合阶段 B 保留策略预算；④ 每日 DB 备份成功且可恢复；⑤ 公网 health 持续 200。达成 → S9 soak 门槛 PASS；否则逐项留痕。

## 阶段 B：云盘保留策略（10-26 ~ 10-29，需一次 Jovi 删除授权）

| # | 操作 | 说明 |
|---|---|---|
| B1 | 写 `docs/planning/RETENTION_POLICY_v1.md` | 三类规则：**pg_dump** 保留最近 3 份+每月 1 日历份（当前 2 份 424M 在窗口内，10-02 的 326M sql.gz 归档为"月度份"）；**镜像** 保留当前+前一版，其余 prune（预期回收约 5.3G）；**release 目录** candidate.yml/image-id/build 日志永久保留（发布证据链），`context/` 与 `context.tar.gz` 保留最近 3 个版本（回收约 0.4-0.5G） |
| B2 | 写 `scripts/ecs_retention_dryrun.sh`（服务器端执行） | 只列清单不动文件：将删除项+将释放空间+保留项核对表 |
| B3 | **Jovi 授权**（决策点 1） | 涉及删除，dry-run 清单呈报后人工批准 |
| B4 | 执行 + 前后 `df`/`du` 差分收据 | 预期净回收 5.5~6G（12G→约 17-18G 可用） |
| B5 | 发布 runbook 追加"备份轮转+镜像 prune"步骤 | 防止复发（当前每发布 +424M 无轮转） |

**不触碰**：另一 AI 的备份/搬迁服务、F 盘本机数据、10-16/10-25 回滚材料、未合并分支对应资产。

## 阶段 C：S8 数据资格（与 soak 并行，10-27 起）

### C-1 F0 真实探测（1–2 个工作日：10-27~10-28）

把 matrix v5 从 DOCS_ONLY 推进到带证据的结论，按 `S8_F0_BOUNDED_PROBE_SPEC_20261002.md` 执行：

1. **AKShare/Eastmoney（免权限，先做）**：F0-01 选两只不同类型 ETF（如 510300 沪深300ETF + 159915 创业板ETF）取原生 5m/15m 各 ≥20 交易日；F0-05 核 volume（股/手）/amount（元）独立单位证据（上游字典+交叉参照）；F0-06 核 bar 闭合/源时间/发布时间；F0-08 核历史深度与调用配额。隔离环境探测，不写生产库。
2. **Tushare（需 token/积分 → 决策点 2）**：仅整理 `etf_mins` 接口的积分门槛与价格选项呈报 Jovi，不注册不采购。
3. **FTShare**：沿用 10-02 资格收据（unqualified），不重复调查。
4. 产出 **matrix v6**（每格 PASS/BLOCKED/UNKNOWN+证据）+ 结论 FEASIBLE / CONDITIONAL / NOT_FEASIBLE_WITHIN_SCOPE。

### C-2 最小资格闭环（F0=FEASIBLE 后约 3 个工作日）

1. PIT 数据集冻结：`build_1430_point_in_time_dataset.py` 跑全历史，产出不可变 PIT 集（含来源/时间戳/缺口清单）。
2. 泄漏审计：`pit_oos_harness` 对五期限预测特征做 PIT 一致性检查（邻居选择、标签、公司行为复权对齐——已入册的 516160 合并与 7 基金拆分在此生效）。
3. 最小 walk-forward 基准：冻结输入与规则 → 时间序列回放 → 与朴素基准（前收/动量）比较 → 含费用滑点。**不改任何策略阈值**；若回放暴露模型问题，产出问题清单而非现场调参。

### C-3 校准评估（约 2 个工作日）

预测概率可靠性曲线、分期限覆盖率与命中校准、阈值敏感度（不自动调阈值）。产出 `calibration_status` 评估报告：`not_calibrated → candidate_calibrated`（须经人工批准才可变）。

### C-4 资格收据与人工决定（决策点 3）

`docs/audits/S8_QUALIFICATION_*.md` 汇总 U01-U19 证据 → **Jovi 独立决定**是否将 `actionable` 从 false 放开（系统不自动晋升）。若 F0=CONDITIONAL：给 Jovi 成本决策单，C-2 起暂停等待，soak 不受影响。

## 阶段 D：贯穿纪律

- 每次实质进展：CHANGELOG/PROJECT_PROGRESS/Hub 三处同步；发布仍走 v1.0.6/1.0.7 的既定机制。
- Jovi 手机实测结论随时回收，并入 Day 7 报告。
- 子 agent 通道恢复后：C-1 的四源探测、B 的清单核对可并行派发。

## 日历总览

| 日期 | 里程碑 |
|---|---|
| 10-26（一） | 新槽首验 + soak Day0/基线 + 观察任务重建 |
| 10-27~28 | S8-F0 真实探测（AKShare/Eastmoney）→ matrix v6；保留策略 v1 + dry-run |
| 10-28~29 | 云盘清理执行（授权后）；两真实交易日判定（Day 2） |
| 10-29~11-02 | PIT 冻结 + 泄漏审计（若 F0 可行） |
| 11-02~11-05 | walk-forward 最小基准；Day 7 soak 中期报告 |
| 11-05~11-10 | 校准评估 |
| 11-13 | Day 14 soak 收官 + S8 资格收据 + actionable 人工决定 → 汇总发布（v1.0.8/1.1.0） |

## 决策点汇总（需 Jovi）

1. **云盘清理授权**（B3，10-28 前后）：批准 dry-run 清单。
2. **付费源决定**（C-1，仅当免费源不合格）：Tushare 积分/FTShare 报价选项。
3. **actionable 最终审批**（C-4，11 月中）：资格收据呈报后人工决定。
4. soak 中途重大失败时的处置确认（重新起算 vs 定点修复继续）。
