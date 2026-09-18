# 本地 Codex 桥接（最小可用切片）

本地 Codex 只解释已导出的证据包，产出**待人工审核的文本候选**。它不能写持仓、不能计算官方五档动作、不能改指标/预测、不能自动续费。

上游设计吸收自 Vibe-Research 的隔离 `CODEX_HOME` / 预算 / 证据事件，以及 vibe-astock 的“硬指标在模型外、LLM 只叙述”。运行时不 vendor 这些仓库。

## 边界

- 专用目录：`--root` 必须是独立目录，不能是 `$HOME`、`~/.codex` 或当前仓库根。
- 子进程环境：`HOME` / `USERPROFILE` / `CODEX_HOME` 只给 Codex 子进程；不要改父 PowerShell。
- 版本钉死：仅接受 `codex-cli 0.149.0`。未知版本失败，不删除门禁。
- 费用：`work` / `run-codex` 必须带 `--approve-execution`。一次进程最多 1 个任务。合法结果上传失败只重传，不二次调用模型。
- `doctor` 不读取 `auth.json`，不声称已登录。`doctor` 的 `live_ready` 固定为 false。

自动化测试只覆盖离线 `doctor` 和未带 `--approve-execution` 的拒绝路径。它们**不能**代替下面的真人步骤，也不能把 `paired: true`（本地有 device.secret）当成公网配对或付费成功。

## Fei 醒后必须亲自完成的现场清单

在 Windows 本机、指向真实 Codex 二进制和真实 HTTPS 源点执行。任何 Cloud Agent / pytest 通过都不算完成。

1. **确认隔离根目录**  
   使用独立目录，例如 `E:\AI_Tools\Other\ETF-Agent-Bridge`。不要改父 PowerShell 的 `HOME` / `USERPROFILE`。

2. **如使用 E: 盘，先检查 NTFS ACL**  
   目录须为本人 SID 所有、已保护、无 Everyone/Authenticated Users 继承读取。可用现有 `windows_private_directory` 路径或本机 `icacls` 核对。ACL 不合格时停止，不要为跑通而放宽。

3. **doctor（只检查卫生，不登录）**

```powershell
$root = 'E:\AI_Tools\Other\ETF-Agent-Bridge'
.\.venv\Scripts\python.exe bridge/etf_agent_bridge.py --root $root doctor
```

期望：`model_login=not_inspected`，`live_ready=false`，`requires_approve_execution=true`。不要根据退出码 0 声称已登录。

4. **官方登录（交互，钉死 0.149.0）**

```powershell
.\.venv\Scripts\python.exe bridge/etf_agent_bridge.py --root $root login --binary <已审 0.149.0 二进制>
```

必须看到官方登录流程完成。未知 CLI 版本失败；不要换版本绕过。

5. **服务端开关**  
   生产/本机服务配置 `WORKSPACE_BRIDGE_ENABLED=true`。浏览器设置页生成一次性配对码。

6. **HTTPS 配对**

```powershell
.\.venv\Scripts\python.exe bridge/etf_agent_bridge.py --root $root pair --origin "https://<你的站点>"
```

明文 HTTP、带用户名密码的 URL、query token 都会被拒绝。配对码不回显。

7. **领取任务（仍不调用模型）**

```powershell
.\.venv\Scripts\python.exe bridge/etf_agent_bridge.py --root $root claim
```

8. **一次付费批准后的 work**  
   明确知道将产生费用后再执行。每个进程最多 1 个任务：

```powershell
.\.venv\Scripts\python.exe bridge/etf_agent_bridge.py --root $root work --model <本次批准的模型> --max-jobs 1 --max-minutes 15 --approve-execution
```

没有 `--approve-execution` 必须失败且不得调用模型。合法 `result.json` 上传失败只重传，不二次付费。

9. **人工审核候选**  
   产出是待审核文本，不是操作信号。`actionable` 保持 false。

## 本机命令摘要

```powershell
$root = 'E:\AI_Tools\Other\ETF-Agent-Bridge'
.\.venv\Scripts\python.exe bridge/etf_agent_bridge.py --root $root doctor
.\.venv\Scripts\python.exe bridge/etf_agent_bridge.py --root $root login --binary <已审 0.149.0 二进制>
# 设置页生成一次性配对码后：
.\.venv\Scripts\python.exe bridge/etf_agent_bridge.py --root $root pair --origin "https://<你的站点>"
.\.venv\Scripts\python.exe bridge/etf_agent_bridge.py --root $root claim
.\.venv\Scripts\python.exe bridge/etf_agent_bridge.py --root $root work --model <本次批准的模型> --max-jobs 1 --max-minutes 15 --approve-execution
```

网页设置页的命令片段与上述一致。本仓库测试没有完成登录、配对或付费。
