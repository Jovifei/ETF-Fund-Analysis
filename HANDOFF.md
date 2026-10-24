# 当前工程交接

2026-10-25。目标：本地 F 盘存真实数据并定时确定性计算，仅将有界展示结果推网站；账号与持仓保留云端隔离，不自动交易。

## 当前事实

- main/origin main：`6a4aa10b565c289a60c63ea16516f6d7f8c40844`（v1.0.6）。PR55 已由 Jovi 于 10-24 合 main（`1e5294d`）；本地验收收据（PR53/54/55）与远端交接文档已入册。
- 生产：`etf.joviluma.com` 运行 v1.0.6，三容器统一镜像 `sha256:69e60fef…`；切换前实测为 api `1a4b665` + worker/scheduler `freshness-825767c`（旧文档所记 9fe 已过期，勿再引用）。服务器发布机制：`release-*/candidate.yml` 分层链，本批新增 `release-v1-0-6-6a4aa10-20261025/`（含 `up.sh`/`rollback.sh`）。
- 本机任务：两任务 Action 已指向 `E:\worktrees\etf-v1-0-6-6a4aa10`，手动运行 0；`--expected-sha` 必须始终等于该工作树 HEAD。
- 版本记录：根目录 `CHANGELOG.md` 为唯一版本入口，发布必须同步更新四处版本并跑 `test_release_version.py`。

## 下一顺序

1. 10-26（周一）起观察自然定时触发、真实收盘 34 覆盖、尾盘 120 秒与两个真实交易日云端零增长；用 job ledger 实测分项耗时。
2. Jovi 手机/正常登录实测（入口 `https://etf.joviluma.com`）：总览同代读取、市场上下文状态、K 线、DPR2/标签叠字/不等价价格口径。
3. 调度容量协调：任务约 6 分 38 秒长于最密 5 分钟 slots，基于 ledger 实测决定提速或快路径；不改算法阈值。
4. Hub Win10061 修复后按契约补报；云盘旧数据保留策略、npm 余量（2 moderate/1 low）另行安排。

数据根 `F:\ETF_Data\ETF-Fund-Analysis`：`db/research.sqlite3`、`state/schedule.sqlite3`、`outbox` 分别为研究数据、执行台账、包与回执。保护 Owner 修改、私有配置/DB/持仓、任务及回滚资产；不 reset/clean/stash，不回显凭据。S0–S9 进度 JSON 是正式台账，生成 MD/HTML 不手改。

## 浏览器认证部署契约（必须保留）

生产保持AUTH_ENABLED=true，持久DATABASE_URL不替换成展示库；AUTO_CREATE_SCHEMA=false，HTTPS AUTH_COOKIE_SECURE=true。首次由auth-bootstrap-admin初始化管理员，已有用户/持仓保留，浏览器正常登录。禁止回显凭据。

新一致备份、不可变源码/镜像和回滚材料齐备并获准后才能切换，失败受控回退。见[部署手册](docs/ALIYUN_DEPLOYMENT.md)。持续UNKNOWN/actionable=false/not_calibrated，不自动交易。
