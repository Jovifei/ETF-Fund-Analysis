# 当前工程交接

2026-10-24。目标：本地 F 盘存真实数据并定时确定性计算，仅将有界展示结果推网站；后续 App 复用，账号与持仓保留云端隔离。

## 接力状态

- main/origin main：`1a4b6652f49c412145d12812fa02820ba0a80991`。
- 已推整合源码：`ba86baf9f10a43531e09538622cad825afbcc89d` / tree `7b34ecedbd4d63f4483f92930eed9c64288645ed`，`codex/local-chain-repair-20261023` / PR51；包含网页 GPT PR53 `f89b382` 的接收证明、同代消费和请求隔离修复。PR52 是独立文档归纳，基于 PR51。
- Jovi 已授权两项缺口、CI、原网站读取/收盘刷新及最小 Vite7.3.7 安全升级。先测后修，最终测试与网页 GPT 复审通过才合 main；**不自动部署**。
- 本批135后端组合、228 Vue、类型/构建/静态、44隔离Mock smoke、18窄屏及6认证回放通过；完整后端/精确CI未最终核定；不能继承旧2545/24为新源码结果。
- 原目录用户文档/未提交文件、F盘数据库/私有配置、正式Windows任务、服务器另一AI备份搬迁及回滚资产保持；不reset/clean/stash，不回显凭据。

## 下一顺序

1. 认证6项与窄屏18项已通过，收齐ee6513a固定后端完整测试与最终精确CI；保留原RED/中断结果。
2. 使用同一“基金决策”普通Chat，以GitHub固定提交与真实收据完成网页GPT复审；不能以连接成功代替审查通过。
3. 精简文档与候选一并复核，按已授权条件合main，并保留原目录Owner改动；不部署、不切正式生产任务。
4. 后续真实收盘34覆盖、公网正常同代消费、尾盘120秒、本人手机、自然两交易日和云端零增长单独验收；不把Mock/HTTP200/单次accepted冒称这些通过。

数据根 `F:\ETF_Data\ETF-Fund-Analysis`：`db/research.sqlite3`、`state/schedule.sqlite3`、`outbox`分别为研究数据、执行台账、包与回执。10月23日已核包过期且收盘刷新失败的原始证据见保留审计；生产实际SHA本批未重验。

核心：[README](README.md)、[运行指南](QUICKSTART.md)、[架构](docs/ARCHITECTURE.md)、[本批整合](docs/audits/TRUSTED_CONTEXT_INTEGRATION_20261024.md)。

## 浏览器认证部署契约（必须保留）

生产保持AUTH_ENABLED=true，持久DATABASE_URL不替换成展示库；AUTO_CREATE_SCHEMA=false，HTTPS AUTH_COOKIE_SECURE=true。首次由auth-bootstrap-admin初始化管理员，已有用户/持仓保留，浏览器正常登录。禁止回显凭据。

新一致备份、不可变源码/镜像和回滚材料齐备并获准后才能切换，失败受控回退。见[部署手册](docs/ALIYUN_DEPLOYMENT.md)。持续UNKNOWN/actionable=false/not_calibrated，不自动交易。
