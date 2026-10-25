# 当前项目状态

2026-10-25 **v1.0.7 已受控发布**（当日第二版）：发布源码 `dcffa8e`（main 已有后续文档提交），生产三容器统一镜像 `sha256:d85d40cd…`，10-25 本次只读公网 `https://etf.joviluma.com` health `version=1.0.7`。本版内容：**16:40/17:40 晚间结算重试槽**（台账证据：15:15 槽收盘 0/34、16:10 槽 3–6/34 每日 FAILED，收盘后数据源渐进发布；密集快槽实测约 125 秒无容量冲突）；vitest 4.1.12/esbuild 0.28.2 官方安全修复后 **npm audit 0 漏洞**；修复 `test_audit_release` 硬编码版本。schema `f0e1d2c3b4a5` 未变；DB 备份恢复校验通过；`rollback.sh` 一键回 v1.0.6。收据：`docs/audits/RELEASE_1_0_7_20261025.md`；版本记录入口：根目录 `CHANGELOG.md`。

2026-10-25 早间 **v1.0.6 已发布**：PR53/54/55 修复链上线（`6a4aa10`，镜像 `69e60fef…`），收据 `docs/audits/RELEASE_1_0_6_20261025.md`。重要更正：切换前生产实为 api `1a4b665`（旧文档所记 9fe 已过期），已统一并如实记载。

个人 ETF/LOF 研究工作台：真实历史与确定性计算保留本机 F 盘，网站消费有界展示包，账号与持仓隔离云端。不自动交易，未校准预测不是操作依据。

**重要更正**：此前"生产=9fe（10-16）"的记载已过期——服务器按主题镜像逐次推进，本轮切换前实测 api=`1a4b665`、worker/scheduler 更旧（freshness-825767c），已统一。服务器另有其他项目容器与另一 AI 备份服务，未触碰；api 历史 RestartCount=57（无 OOM、退出码 0）成因未深查，recreate 后归零观察。

本机计算任务 `ETF-Local-Live-Compute` 与 `ETF-Local-Reconcile-1630` 已仅迁移 Action 至干净工作树 `E:\worktrees\etf-v1-0-7-dcffa8e`（`--expected-sha=dcffa8e…`，Principal/触发器保留）；Trigger1 轮询窗口延至 4.5 小时覆盖 17:40 槽；手动运行 LastResult=0。

未完成门槛：**周一（10-26）起验证 16:40/17:40 新槽首次实跑与当日结算落地**、自然触发与两个真实交易日；正常认证用户页面与本人手机/DPR2/标签叠字/价格口径由 Jovi 实测；7–14 日 soak；S8 数据资格保持 `UNKNOWN / actionable=false / not_calibrated`；云盘约 1.13GB 旧数据保留策略；子 agent 通道（GLM-5.3-Flash 供应商不可用）。

资格保持 UNKNOWN、actionable=false、calibration_status=not_calibrated；自动交易关闭。
