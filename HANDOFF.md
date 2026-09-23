# 当前接手入口：R1 与 A-U1–A-U3 生产版（2026-09-23）

先读 `AGENTS.md`、本页、`STATUS.md`、[本次生产收据](docs/PRODUCTION_DEPLOYMENT_RECEIPT_AU_20260923.md)、[A-U1–A-U3 接收合同](docs/UI_ACCOUNT_HANDOFF_20260923.md)。当前部署源码固定为 `0dbd3fee58a3f5e080aacbcd8eae8d5964aec54f`，tree 为 `f8607b3de8decde6065ccc559c5c26b0262b8e6b`，镜像 ID 为 `sha256:251a0623c694b07525bd398b52f41eecc17ec3d1216912c6d593b704fc8ae81a`；API/worker/scheduler 同镜像，数据库 head `e609200001`。R1 在此前已合并；本次 A-U1–A-U3 与构建/运维脚本修复随后快进到 `main`。

本次没读取或修改生产业务行，没有刷新真实 Provider，也没有重标 certified/hash/原始 OHLCV。真实数据资格保持 **UNKNOWN**，不能从健康检查或 CI 通过推导交易资格。接下来按顺序完成 R2 更新及时性、R3 详情空态/决策解释、R4 价格研究基准和完整缠论、R5 真人本地 Codex；真实数据复审和后续发布作为 R6 单独授权。账户邮箱/短信/微信验证、找回和永久删除仍未实现；当前账户关闭只停止登录并保留数据。

## 原有数据保护与回滚合同

## 认证与数据保护合同

正式服务必须保持 AUTH_ENABLED=true，DATABASE_URL 从仓库外私有配置读取，AUTO_CREATE_SCHEMA=false，通过 Alembic 迁移。正式 HTTPS 使用 AUTH_COOKIE_SECURE=true；本地回环 HTTP 的 Cookie 例外不得复制到生产。浏览器使用数据库账户/会话，不复活旧 Bearer 认证。auth-bootstrap-admin 仅限已确认的新空库，由本人安全输入；原库不得重新初始化或重置已有管理员。任何 pytest/seed/清库工具不得指向真实持仓数据库。

独立 clone/worktree 接收，保留原工程脏改动；不 reset/clean/stash，不强推。备份原库和私有报告，先恢复到副本演练。只读诊断：

```powershell
.\.venv\Scripts\python.exe scripts/audit_research_inputs.py --codes 510300.SH 512480.SH 588200.SH --output E:\ETF_Private\audit-new.json
```

必须先安全加载指向副本的 DATABASE_URL。输出文件不能已存在。此命令没有 Provider 调用、SQL 写入或资格提升；退出0仍需检查 items[].blockers 和 indicator_blockers。Windows 输出目录ACL由本地接收者先检查。

## 验收顺序

第二真实源 bounded probe → 同日量额/单位对账 → 按目标交易日抓取和衍生任务 → PIT/OOS walk-forward → 14:30 前瞻观察 → 人工批准。日线截止统一 15:15，不把 15:01 取得的昨日数据记成今日完成。指数 OHLC 与实时观察是不同数据路径。

当前 FTShare 的 Skill 路由实测为 `etf-ohlcs=404`、`etf-candlesticks=405`；应用内固定 Provider 对五只 ETF 的列表、日线、现价探测均为 `CapabilityUnavailable`。不得手工把 `FTSHARE_QUALIFICATION` 改成 `qualified`。资格脚本修复后，即使三项接口都有记录，只要缺独立单位或 operational-grade 时间证据，顶层状态仍必须是 `unqualified`。

API/worker/scheduler须同版本、同有效库，SQLite通过现有文件锁串行流水线及短事务；不把WAL称为无限并发写入或网络文件共享方案。旧路径的写入者必须停止重复调度。优先利用专用PostgreSQL测试与实际部署策略。

Bridge 登录使用 bridge/etf_agent_bridge.py 的 login 子命令；不要改父PowerShell的 HOME/USERPROFILE。CLI仍严格固定0.149.0，未知版本需独立审阅，不能删除门禁。启用、本人登录、费用确认与最多一次work在现场完成。合法已生成产物重传不得再跑模型，损坏结果显式失败，不修改lease来重付费。醒后逐步清单见 [docs/LOCAL_CODEX_BRIDGE.md](docs/LOCAL_CODEX_BRIDGE.md)；pytest/`doctor` 退出 0 不是登录、配对或付费成功。

不直接按系数修改新浪量额或原始价格。已登记的官方基金份额拆分事件（见 `docs/audits/CORPORATE_ACTIONS_20260920.md`）只允许在内存研究序列中按证据生成复权视图；公告证据、端点单位合同、原始记录与独立研究序列必须分开。没有完整证据仍维持研究阻断。新版本会使部分“看起来正常”的旧数据暴露缺口，这是安全修正而不是让接手者清掉异常。

## 回滚与范围

无生产部署授权时，只做本地/隔离验收。需要上线另行批准；任何数据迁移先备份和恢复演练。不要把恢复旧数据/旧代码用来绕过新资格门禁。恢复备份前保护其后新增的持仓、自选、复盘与审阅写入。模型API主密钥、账户凭据、行情Token不得进入Git、聊天或截图。

[旧交接全文](docs/archive/pre-audit-close-20260913/HANDOFF.md)仅保留历史，不覆盖以上规则。完整缠论、自动训练、支付订阅、自动云地同步仍未实现。
