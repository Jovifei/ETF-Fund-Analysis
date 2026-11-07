# 本机 SMTP 安全配置

用途：给 ETF 定时邮件设置无人值守发送通道。授权码只由你在自己的终端隐藏输入，使用 Windows CurrentUser DPAPI 加密并保存在 F 盘私有目录；不写入聊天、仓库、命令参数或日志。

## 1. 终端配置（首选安全通道）

在大机终端执行以下命令：

```powershell
& 'E:\project\ETF-Fund-Analysis\.venv\Scripts\python.exe' 'E:\project\ETF-Fund-Analysis\scripts\run_local_notifications.py' configure --root 'F:\ETF_Data\ETF-Fund-Analysis' --confirm-owner-switchover
```

如果已有配置需要重新更新，追加 `--overwrite` 参数：
```powershell
& 'E:\project\ETF-Fund-Analysis\.venv\Scripts\python.exe' 'E:\project\ETF-Fund-Analysis\scripts\run_local_notifications.py' configure --root 'F:\ETF_Data\ETF-Fund-Analysis' --confirm-owner-switchover --overwrite
```

依次输入：
- SMTP登录邮箱（如 QQ/163 邮箱）
- SMTP服务器（如 smtp.qq.com / smtp.163.com）
- TLS端口（465 或 587）
- 对应模式（ssl 或 starttls）
- 收件邮箱（回车默认使用登录邮箱）
- 邮箱授权码（隐藏输入，终端不回显）

## 2. 启用 / 停用发送通道

配置保存后，如需单独开启或关闭发送，无需重新输入密码：

- **开启发送**：
  ```powershell
  & 'E:\project\ETF-Fund-Analysis\.venv\Scripts\python.exe' 'E:\project\ETF-Fund-Analysis\scripts\run_local_notifications.py' enable --root 'F:\ETF_Data\ETF-Fund-Analysis' --confirm-owner-switchover
  ```
- **停用发送**：
  ```powershell
  & 'E:\project\ETF-Fund-Analysis\.venv\Scripts\python.exe' 'E:\project\ETF-Fund-Analysis\scripts\run_local_notifications.py' disable --root 'F:\ETF_Data\ETF-Fund-Analysis'
  ```
- **查看状态**：
  ```powershell
  & 'E:\project\ETF-Fund-Analysis\.venv\Scripts\python.exe' 'E:\project\ETF-Fund-Analysis\scripts\run_local_notifications.py' status --root 'F:\ETF_Data\ETF-Fund-Analysis'
  ```

## 3. 网页端配置辅助（推送邮箱与 OpenAI Key）

系统在网页工作台提供了 **“⚙️ 推送与AI”** 弹窗：
- 用户登录后可直接绑定个人推送接收邮箱（如 `977191131@qq.com`）；
- 填写 OpenAI API Key 后，每日定时邮件会在确定性指标决策下方追加纯文字事实解读与风险提示（严格禁止模型篡改数值指标或生成交易指令）。
- 密钥与配置均在本机经 DPAPI / AES-GCM 安全加密存储。

## 4. 自动化 Windows 定时任务注册

通过 PowerShell 注册每日定时通知任务（11:40, 14:30, 14:45, 18:00 槽）：
```powershell
powershell -ExecutionPolicy Bypass -File 'E:\project\ETF-Fund-Analysis\scripts\register_local_notification_task.ps1' -Apply
```
注册后任务默认处于 `Disabled` 状态，人工复核后右键启用即可。
