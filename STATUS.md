# 当前项目状态

2026-10-25 **v1.0.6 已受控发布**：main `6a4aa10`（PR53/54/55 修复链 + 验收收据入册 + CHANGELOG + 版本四处联动 1.0.6），生产 api/scheduler/worker 三容器统一镜像 `sha256:69e60fef…`，公网 `https://etf.joviluma.com` health `version=1.0.6`、JS 与本地构建一致、匿名 API 401。schema `f0e1d2c3b4a5` 未变；切换前 DB 备份恢复校验通过；`rollback.sh` 与旧工作树保留。收据：`docs/audits/RELEASE_1_0_6_20261025.md`；版本记录入口：根目录 `CHANGELOG.md`。

个人 ETF/LOF 研究工作台：真实历史与确定性计算保留本机 F 盘，网站消费有界展示包，账号与持仓隔离云端。不自动交易，未校准预测不是操作依据。

**重要更正**：此前"生产=9fe（10-16）"的记载已过期——服务器按主题镜像逐次推进，本轮切换前实测 api=`1a4b665`、worker/scheduler 更旧（freshness-825767c），已统一。服务器另有其他项目容器与另一 AI 备份服务，未触碰；api 历史 RestartCount=57（无 OOM、退出码 0）成因未深查，recreate 后归零观察。

本机计算任务 `ETF-Local-Live-Compute` 与 `ETF-Local-Reconcile-1630` 已仅迁移 Action 至干净工作树 `E:\worktrees\etf-v1-0-6-6a4aa10`（`--expected-sha=6a4aa10…`，Principal/触发器保留；reconcile 按 main 合同补 expected-sha）。手动运行 LastResult=0；view-sync 与新接收端 HTTPS 往返对历史包返回 `already_accepted`（PR53 合同端到端生效）。

未完成门槛：自然定时触发与两个真实交易日（周六无槽，自 10-26 起）；正常认证用户页面与本人手机/DPR2/标签叠字/价格口径由 Jovi 实测；调度容量协调（约 6 分 38 秒 vs 最密 5 分钟 slots）；7–14 日 soak；S8 数据资格保持 `UNKNOWN / actionable=false / not_calibrated`；Hub 上报 WinError 10061；云盘约 1.13GB 旧数据保留策略。

资格保持 UNKNOWN、actionable=false、calibration_status=not_calibrated；自动交易关闭。
