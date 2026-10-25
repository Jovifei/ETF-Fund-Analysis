# 当前项目状态

2026-10-25 晚，**v1.0.12 已受控发布**：提交 `e21bccf`，三服务镜像 `sha256:1863c32d…`（基镜像 v1.0.9），公网 health `version=1.0.12`。修复独立审查（`1a4b665..8e062b7`）的全部 4 项 Important + 6 项 Minor：展示包报价新鲜度单一权威（详情页与自选/持仓定价共用 `bundle_expired`/`bundle_is_stale`/`quote_display_state`，消除 600 秒与整包 TTL 双判据）、缺过期时间 fail-closed、404 细分为 generation/bundle/instrument、持仓未覆盖行改「无快照」、非零退出追加机器可读哨兵、新增展示包身份登记表 `config/bundle_identity_registry.json` 与部署门禁 `scripts/check_bundle_identity.py`、运维手册 `docs/BUNDLE_IDENTITY_AND_WEEKEND_RUNBOOK.md`；四处版本统一 1.0.12，CHANGELOG 补录 [1.0.11]/[1.0.10]。门禁：全量后端 2686 通过/24 跳过/0 失败、前端 typecheck 0 + vitest 228 + 构建成功、部署前后身份门禁均 approved、默认读取 34 条。收据：`docs/audits/RELEASE_1_0_12_20261025.md`。

2026-10-25，**v1.0.9 已受控发布**：PR57 固定源码 `1c1a500` 合入 main `23c20b6`（文件树 `ce9693e`）；生产三服务统一镜像 `sha256:259181a5…`，公网 `/api/health` 返回 `status=ok, version=1.0.9, auth_enabled=true`。变更只涉及本地展示包模式的自选、搜索与持仓报价读取：已批准包覆盖外显示缺价，旧报价不冒充实时；账户份额与成本未修改。完整收据见 `docs/audits/RELEASE_1_0_9_20261025.md`，版本入口为 `CHANGELOG.md`。

网站研究总览默认读取同批次 34 条，当前批次 `1792930789674`（2026-10-25 20:18 发布，有效期至 22:18）；此前批次 `1792913919058`。底层日线截至 2026-10-23（最近交易日）。已接收展示包到期仍可读并标记历史（`is_stale=true`），详情与定价对同一报价返回一致状态。此前空白的直接复现原因是代码身份不匹配，不能单独归因于两小时有效期。

本机窗口治理：`ETF-Local-Live-Compute` 曾按 Jovi 要求删除，随后依 Jovi 明确的“保留执行、不弹窗”更正，用备份 XML 恢复原触发器/参数，仅将执行器换为 `pythonw.exe`；17:15 首次自然触发退出码 0、无新增 Windows Terminal。`ETF-Local-Reconcile-1630` 同样只换为 `pythonw.exe`，下次自然运行待 10-26 验证。药箱的 `MedboxPrivateModel` 改用无控制台 `wscript.exe` 启动原 PowerShell 脚本，17:24 自然触发后 Node/SSH 进程与状态文件正常更新、无新增终端；其 `FORWARD_STARTED_NOT_HEALTH_VERIFIED` 仍不能视为模型健康证明。孤立的 `agent-browser` 自动化 Chrome 已结束，日常 Chrome 保留。

存储位置已只读核账：F 盘研究库最新日线为 10-23（68,962 行），云端 PostgreSQL 的旧日线止于 10-09（22,327 行）；云端仍有旧研究数据，最大 `decision_board_snapshots` 表约 661 MiB。服务器展示包约 232 MiB、上限 320 MiB；发布备份约 1.56 GiB。根盘 40 GiB 中约 28 GiB 已用，主要是 Docker 约 13 GiB、非 Docker 约 15 GiB（含 4 GiB swap 文件）；余约 10 GiB。详见 `docs/audits/STORAGE_LOCATION_AND_DISK_20261025.md`，未做清理。

当前收藏共 6 项：1 项在批准展示包内有历史报价，5 项因不在包内明确缺价；不再读取冻结于 10-09 的云端价格。Jovi 暂以收藏维护所持基金代码；生产持仓表仍为空，份额、成本与持仓盈亏未知，不自动把收藏转换成持仓。因子诊断仍是 09-09 的手动历史工件。

验证：本机完整后端 2,652 PASS / 24 SKIP、退出码 0；最终候选聚焦 17 PASS，前端 228 PASS、类型/构建通过、npm audit 0；PR57 固定 SHA 的全部 CI 成功。生产备份经 `pg_restore --list` 与 SHA-256 校验，回滚入口为 `release-v1-0-9-1c1a500-20261025/rollback.sh`（回 v1.0.8）。候选镜像沿用既有 overlay 发布路径，安装包元数据仍继承旧版 `0.7.0`；运行源码、镜像标签与应用版本已核对，完整重建镜像由 CI 成功证明，后续应统一运行包元数据。

未完成：为 5 个收藏标的建立**不暴露个人收藏清单**的合格报价覆盖；Jovi 正常登录和手机页面实测；10-26 起晚间结算槽自然触发及两个真实交易日、7–14 日观察；S8 数据资格继续 `UNKNOWN / actionable=false / not_calibrated`。本系统不连接券商、不自动交易。
