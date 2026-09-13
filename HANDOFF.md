# 接手入口：v1.0.5 审核修复

先读 AGENTS.md → STATUS.md → docs/README.md → docs/CODE_AUDIT_BLOCKERS_20260912.md → docs/audits/CLOSURE_20260913.md。固定应用 SHA 以本轮验收收据和 Codex 接收 Prompt 为准，不从旧 main 或旧 ZIP 覆盖新修复。最终提交后仍需核对远端分支是否有新增改动。

## 认证与数据保护合同

正式服务必须保持 AUTH_ENABLED=true，DATABASE_URL 从仓库外私有配置读取，AUTO_CREATE_SCHEMA=false，通过 Alembic 迁移。正式 HTTPS 使用 AUTH_COOKIE_SECURE=true；本地回环 HTTP 的 Cookie 例外不得复制到生产。浏览器使用数据库账户/会话，不复活旧 Bearer 认证。auth-bootstrap-admin 仅限已确认的新空库，由本人安全输入；原库不得重新初始化或重置已有管理员。任何 pytest/seed/清库工具不得指向真实持仓数据库。

独立 clone/worktree 接收，保留原工程脏改动；不 reset/clean/stash，不强推。备份原库和私有报告，先恢复到副本演练。只读诊断：

```powershell
.\.venv\Scripts\python.exe scripts/audit_research_inputs.py --codes 510300.SH 512480.SH 588200.SH --output E:\ETF_Private\audit-new.json
```

必须先安全加载指向副本的 DATABASE_URL。输出文件不能已存在。此命令没有 Provider 调用、SQL 写入或资格提升；退出0仍需检查 items[].blockers 和 indicator_blockers。Windows 输出目录ACL由本地接收者先检查。

## 验收顺序

资格拒绝样本与独立真实源对账 → 按目标交易日抓取/衍生任务与重试 → 旧表/详情日期和输入版本一致 → Windows独立登录/ACL与人批准单次任务 → 固定源码/构建/依赖/镜像/迁移收据。日线截止统一15:15，不把15:01取得昨日数据记成今日完成。指数OHLC与实时观察是不同数据路径。

API/worker/scheduler须同版本、同有效库，SQLite通过现有文件锁串行流水线及短事务；不把WAL称为无限并发写入或网络文件共享方案。旧路径的写入者必须停止重复调度。优先利用专用PostgreSQL测试与实际部署策略。

Bridge 登录使用 bridge/etf_agent_bridge.py 的 login 子命令；不要改父PowerShell的 HOME/USERPROFILE。CLI仍严格固定0.149.0，未知版本需独立审阅，不能删除门禁。启用、本人登录、费用确认与最多一次work在现场完成。合法已生成产物重传不得再跑模型，损坏结果显式失败，不修改lease来重付费。

不直接按系数修改新浪量额或588200价格。公告证据、端点单位合同、原始记录与独立复权研究序列必须分开；没有完整证据就维持研究阻断。新版本会使部分“看起来正常”的旧数据暴露缺口，这是安全修正而不是让接手者清掉异常。

## 回滚与范围

无生产部署授权时，只做本地/隔离验收。需要上线另行批准；任何数据迁移先备份和恢复演练。不要把恢复旧数据/旧代码用来绕过新资格门禁。恢复备份前保护其后新增的持仓、自选、复盘与审阅写入。模型API主密钥、账户凭据、行情Token不得进入Git、聊天或截图。

[旧交接全文](docs/archive/pre-audit-close-20260913/HANDOFF.md)仅保留历史，不覆盖以上规则。完整缠论、自动训练、支付订阅、自动云地同步仍未实现。
