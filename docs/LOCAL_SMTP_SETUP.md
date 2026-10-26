# 本机 SMTP 安全配置

用途：给 ETF 定时邮件设置无人值守发送通道。授权码只由你在自己的终端隐藏输入，使用 Windows CurrentUser DPAPI 加密并保存在 F 盘私有目录；不写入聊天、仓库、命令参数或日志。配置工具已通过合成授权码的真实加密往返测试，尚未发送真实邮件。

## 在你自己的终端执行

```powershell
& 'E:\project\ETF-Fund-Analysis\.venv\Scripts\python.exe' 'C:\Users\Admin\.codex\worktrees\watchlist-quote-source\ETF-Fund-Analysis\scripts\run_local_notifications.py' configure --root 'F:\ETF_Data\ETF-Fund-Analysis' --confirm-owner-switchover
```

依次输入：SMTP登录邮箱、邮箱服务商提供的SMTP服务器、TLS端口（465/587）、对应模式（ssl/starttls）、收件邮箱、邮箱授权码。授权码使用 getpass 隐藏输入；不要使用聊天传递，不要把完整终端输入截图发送。QQ/163等邮箱需在各自官方邮箱设置中取得授权码。

`--confirm-owner-switchover` 表示以项目 SMTP 作为唯一自动发送方；旧 Bot 的同槽邮件草稿不再手动批准重复发送。如果还没决定迁移归属，先去掉该标记完成默认关闭的配置。

本命令没有 `--enable`，所以**只保存配置，不发送邮件，也不启动定时任务**。真实发送将在代码复核、固定版本测试与切换检查通过后启用。

成功时只显示 `state=CONFIGURED`、启用/归属布尔值和配置路径，不显示邮箱或授权码。私有路径：`F:\ETF_Data\ETF-Fund-Analysis\config\notifications\smtp.json`。不要把此文件加入 Git。若已有配置，工具会拒绝覆盖，保留原文件。

配置完成后在聊天回复“已在本机配置”即可，不需要提供邮箱或授权码。定时执行必须使用同一个 Windows 用户，其他账户无法解密该授权码；正常运行仍保持 pythonw 无弹窗。
