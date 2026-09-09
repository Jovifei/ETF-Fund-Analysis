# v1.0.4 AI连接、安全与会员边界

## 配置一次，按需调用

`GET /api/workspace/ai/profiles` → `POST/PUT /profiles` → `POST /{id}/default` → 明确 `confirm_cost=true` 的 `/test` 或 `/run`。测试或分析都是队列任务，API接收后返回202，不能把202当模型完成。所有配置按真实数据库用户隔离，不支持旧Bearer代替用户存储Key。Key输入不会出现在校验错误、GET结果或任务负载，修改Key留空表示保留原值；删除清除密文，不删旧报告。

Windows初始化示例（在实际运行服务的用户下）：

```powershell
python scripts/create_ai_secret_store.py --path E:\ETF_Private\ai\master.key
# 在仓库外的私有配置中设置路径，不在聊天或Git记录密钥：
# WORKSPACE_AI_KEY_FILE=E:\ETF_Private\ai\master.key
# WORKSPACE_AI_API_ENABLED=true
```

Linux主密钥必须在仓库外绝对路径，父目录700、文件600、当前进程用户拥有；不要覆盖既有密钥。Docker应事先在私有宿主目录创建文件，并通过独立生产override以只读方式挂载到API与worker相同路径，设置KEY_FILE指向容器路径。先确认镜像运行UID并设置匹配权限，不将700目录改成777解决错误；基础Compose默认不自动挂载任何私人目录。

Windows密钥使用CurrentUser DPAPI保护；导出到另一用户或Linux后不能解密。完整凭据迁移需要在原机器重新安全输入新系统，不复制auth.json。AES-GCM使用用户与profile ID绑定附加认证数据。数据库备份与主密钥备份分别私有保管；无轮换自动迁移功能，删除主密钥即无法读取已存配置。

## 网络、预算与不可信输出

默认只允许管理员批准的 `https://api.openai.com`、`https://api.deepseek.com`；额外服务需配置 `WORKSPACE_AI_ALLOWED_ORIGINS`。只接受HTTPS443固定base路径（包括compatible-mode/v1），拒绝userinfo/query/fragment、私网解析、重定向及环境代理，不开放任意URL、工具或Shell。域名批准是信任边界；DNS预检不是连接IP固定，部署仍应使用出站网络策略，不承诺抵御受信域名主动DNS重绑定。

Token参数自动按OpenAI选max_completion_tokens、其他兼容服务选max_tokens，也可显式配置；不兼容时由用户修改后手动重试，不能自动重复付费。连接测试上限256输出Token；研究128–4000，输入100KB、响应200KB；连接和读取均超时，90秒响应读取截止、worker外层时限。单队列最多10项，免费用户滚动24小时5次、Plus/admin30次，连接测试和失败均占次数。不依据本地Codex订阅推断API免费。

研究输入只来自本系统冻结证据（可选持仓需原先显式同意）；模型输出仅候选。JSON格式、job/hash/model/producer、引用集合、过期、租约、用户状态与配置revision再校验。不补造错误JSON，不自动执行模型工具，不把AI输出写入MACD/KDJ/支撑压力/当前动作。后台失败保留分类，不记录含密钥的原异常。已排队任务被取消、配置删除、用户停用或权益变化均在执行前/接受时再次检查。收到取消时已发生的外部请求无法撤销计费，但不能发布其迟到结果。

## 会员与用户

plan=free/plus和role=member/admin独立。移除为可恢复停用，保留持仓与报告；最后活跃管理员保护；角色变化撤销会话，管理员操作留净化审计。权益默认关闭；开启后可将api_research/factor_research/monthly_research限制为Plus，接口与工作器检查，不只是前端隐藏按钮。没有付款结算、订单、到期自动降级、多租户商业SLA或对全部历史文件的通用DRM。

## 本地Codex不是服务器Shell

配置沿用 `bridge/bridge.py` 的配对、签名、任务/租约及型号版本门禁。按AI研究页步骤执行：独立CODEX_HOME登录→设备配对→doctor→最多1个10分钟任务。网站不读取本机凭据，不自动访问localhost；不要求用户另写MCP。Vibe固定安装器和产物适配继续独立，未默认运行完整第三方服务栈。
