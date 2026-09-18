# 本地 Codex 桥接（最小可用切片）

本地 Codex 只解释已导出的证据包，产出**待人工审核的文本候选**。它不能写持仓、不能计算官方五档动作、不能改指标/预测、不能自动续费。

上游设计吸收自 Vibe-Research 的隔离 `CODEX_HOME` / 预算 / 证据事件，以及 vibe-astock 的“硬指标在模型外、LLM 只叙述”。运行时不 vendor 这些仓库。

## 边界

- 专用目录：`--root` 必须是独立目录，不能是 `$HOME`、`~/.codex` 或当前仓库根。
- 子进程环境：`HOME` / `USERPROFILE` / `CODEX_HOME` 只给 Codex 子进程；不要改父 PowerShell。
- 版本钉死：仅接受 `codex-cli 0.149.0`。未知版本失败，不删除门禁。
- 费用：`work` / `run-codex` 必须带 `--approve-execution`。一次进程最多 1 个任务。合法结果上传失败只重传，不二次调用模型。
- `doctor` 不读取 `auth.json`，不声称已登录。

## 本机步骤

```powershell
$root = 'E:\AI_Tools\Other\ETF-Agent-Bridge'
.\.venv\Scripts\python.exe bridge/etf_agent_bridge.py --root $root doctor
.\.venv\Scripts\python.exe bridge/etf_agent_bridge.py --root $root login --binary <已审 0.149.0 二进制>
# 设置页生成一次性配对码后：
.\.venv\Scripts\python.exe bridge/etf_agent_bridge.py --root $root pair --origin "https://<你的站点>"
.\.venv\Scripts\python.exe bridge/etf_agent_bridge.py --root $root claim
.\.venv\Scripts\python.exe bridge/etf_agent_bridge.py --root $root work --model <本次批准的模型> --max-jobs 1 --max-minutes 15 --approve-execution
```

服务端需 `WORKSPACE_BRIDGE_ENABLED=true`。网页设置页的命令片段与上述一致。现场登录、配对和付费确认仍须本人完成；本仓库测试只覆盖不调用真实模型的门禁。
