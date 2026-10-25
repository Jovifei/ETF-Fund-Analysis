# 当前工程交接

2026-10-25。目标：本地 F 盘存真实数据并定时确定性计算，仅将有界展示结果推网站；账号与持仓保留云端隔离，不自动交易。

## 当前事实

- 本次查收基线 main@`18686f112d04e91756ebed2ca6e865aae7c58dcf`（v1.0.7 后续文档提交）；PR55 于 10-24 合入的 `1e5294d` 是其祖先，本地验收收据和远端交接文档已入册。后续文档提交会推进 main 指针，须以实时 Git ref 为准。
- 生产：10-25 本次只读 health 返回 `status=ok`、`version=1.0.7`；受控发布收据绑定源码 `dcffa8e`、三容器镜像 `sha256:d85d40cd…`。schema 不变；分层发布与回滚路径见 `docs/audits/RELEASE_1_0_7_20261025.md`。health 不代替正常认证用户或自然调度验收。
- 本机任务：10-25 只读核两任务 Action 均指向 `E:\worktrees\etf-v1-0-7-dcffa8e`、`--expected-sha=dcffa8e…`，状态 Ready；Trigger1 重复窗口为 PT4H30M 覆盖 17:40。发布收据记手动运行 LastResult=0，首次自然触发待 10-26 核验。
- 版本记录：根目录 `CHANGELOG.md` 为唯一版本入口，发布必须同步更新四处版本并跑 `test_release_version.py`。

## 下一顺序

1. 10-26（周一）起核 16:40/17:40 新槽首跑、当晚真实收盘 34 覆盖、自然定时触发及两个真实交易日云端零增长；用 job ledger 实测分项耗时。
2. Jovi 手机/正常登录实测（入口 `https://etf.joviluma.com`）：总览同代读取、市场上下文状态、K 线、DPR2/标签叠字/不等价价格口径。
3. 密集快槽已实测约 125 秒，旧“6 分 38 秒挤占五分钟槽”担忧不再作为当前阻断；重点观察晚间结算重试是否真正取得当日日线，失败按 ledger 定因，不改算法阈值。
4. Hub Win10061 恢复后按契约补报；云盘旧数据保留策略和 7–14 日 soak 另行执行。v1.0.7 锁文件安全审计为 0 漏洞。

数据根 `F:\ETF_Data\ETF-Fund-Analysis`：`db/research.sqlite3`、`state/schedule.sqlite3`、`outbox` 分别为研究数据、执行台账、包与回执。保护 Owner 修改、私有配置/DB/持仓、任务及回滚资产；不 reset/clean/stash，不回显凭据。S0–S9 进度 JSON 是正式台账，生成 MD/HTML 不手改。

## 浏览器认证部署契约（必须保留）

生产保持AUTH_ENABLED=true，持久DATABASE_URL不替换成展示库；AUTO_CREATE_SCHEMA=false，HTTPS AUTH_COOKIE_SECURE=true。首次由auth-bootstrap-admin初始化管理员，已有用户/持仓保留，浏览器正常登录。禁止回显凭据。

后续版本仍须先核一致备份、不可变源码/镜像及回滚材料，再按独立授权切换；v1.0.7 当前回滚入口见 `docs/audits/RELEASE_1_0_7_20261025.md`。见[部署手册](docs/ALIYUN_DEPLOYMENT.md)。持续UNKNOWN/actionable=false/not_calibrated，不自动交易。
