# 本地部署、真实数据和研究 Bridge

先看 [START_HERE](../START_HERE.md) 的临时演示；这里是保存真实数据的独立部署。本文操作并未替用户执行。

## 前置条件

Python3.12建议用于项目与Vibe；前端重建/Vibe需Node≥22.18。Docker部署需要可用的Docker Engine/Compose和联网安装依赖。
ZIP的 `backend/app/workspace_dist` 已构建，可只安装Python先看界面；Git默认忽略生成目录，提交后Docker/CI会从Vue源码重新构建。

## Docker：独立项目和数据卷

在项目根目录，将 `deploy/workspace.env.example` 复制为 **被Git忽略的** `deploy/workspace.env`。
自行设定随机URL-safe数据库密码，不能使用示例占位值；不要将内容贴到聊天、截图或提交。
初次UI验收可选 `MARKET_PROVIDER=mock`，真实使用改 `public_composite` 或经过验证并已配置的provider；始终 `ALLOW_MOCK_FALLBACK=false`。

```bash
docker compose --env-file deploy/workspace.env -f deploy/compose.workspace.yml config --quiet
docker compose --env-file deploy/workspace.env -f deploy/compose.workspace.yml up -d --build
docker compose --env-file deploy/workspace.env -f deploy/compose.workspace.yml exec api fund-decision auth-bootstrap-admin
```

管理员创建通过交互完成，无默认管理员密码。API会在新数据库上执行Alembic到 `d40609090002`。
只开放 `127.0.0.1:8081`，数据库不暴露宿主端口；项目/volume名与旧生产分离。页面为Cookie会话+CSRF，不用浏览器localStorage保存认证。
检查 `/api/health` 后登录，在设置页发起有界数据任务；状态页显示队列/worker进度，页面打开不拉取全市场历史。
真实Provider接口、许可、流量和覆盖率需实际环境检查；服务启动成功不代表完整ETF目录或实时行情已准备好。

```bash
docker compose --env-file deploy/workspace.env -f deploy/compose.workspace.yml logs --tail 100 api worker scheduler
docker compose --env-file deploy/workspace.env -f deploy/compose.workspace.yml stop
```

不要执行 `down -v` 作为普通停止，它会删除真实数据卷。公开HTTPS部署时设置 `APP_ENV=production` 与 `AUTH_COOKIE_SECURE=true`，反向代理、TLS、备份和回滚单独验收。
现有 `docker-compose.yml` 保留用于旧部署；不要把两个Compose文件无审查地合并成一套生产服务。

## Vibe：独立试验，不进入主站运行依赖

固定上游commit：`09e8404a33ba0d05e036e01207be4701c61d692c`。
先只读体检；安装命令必须显式允许网络，使用全新专用目录，脚本拒绝覆盖未托管目录：

```powershell
.\.venv\Scripts\python.exe scripts/vibe_trial.py doctor --root E:\AI_Tools\Other\Vibe-Research
.\.venv\Scripts\python.exe scripts/vibe_trial.py install --root E:\AI_Tools\Other\Vibe-Research --allow-network-install
.\.venv\Scripts\python.exe scripts/vibe_trial.py verify --root E:\AI_Tools\Other\Vibe-Research
```

脚本不登录、不运行真实模型，不接主站数据库。使用独立VRA_DATA_ROOT/CODEX_HOME、清洁环境、时间预算及产物manifest。verify运行上游编排器/前端测试和构建、计算测试，失败保留失败。
当前容器未完成此安装；历史独立runner曾出现编排器测试失败，不能认定“安装好就完整合格”。
上游原生公司研究不自动等于ETF专属研究。真实模型验证需在官方登录后另行执行，并保存实际来源/状态/费用；不得共享或上传认证文件。

## 原生 Vibe 结果进入网站（无需给Vibe数据库权限）

只读取单次运行目录中的 `manifest.json/report.md/evidence.json/calculations.json/conflicts.json`。
先人工检查隐私，再运行以下命令；时间、代码、模型和版本必须填写该次真实运行的事实，不能沿用示例：

```powershell
.\.venv\Scripts\python.exe bridge/export_vibe.py "<单次运行目录>" `
  --output "<新的输出路径>.json" --kind etf --ts-code 512480.SH `
  --source-as-of "<带时区的证据截止时间>" --run-id "<真实运行ID>" `
  --producer-version "<真实上游commit>" --model "<真实模型标识>" `
  --upstream-status complete --confirm-public-data
```

缺失/过期运行必须分别使用 `incomplete` / `stale`；failed不可伪装complete。网站AI研究页的“导入外部研究包”先验证预览，再确认导入，最后由所有者批准或拒绝候选。
此通路是归档外部产物，不是把任意报告冒充本网站已发任务的执行结果。研究资格始终独立。

## 本地 Bridge 主动回传

推荐先手工导出固定证据任务并导入结构化结果，通过后才启用 `WORKSPACE_BRIDGE_ENABLED=true`。
网页设置页生成一次性配对码。Python客户端从隐藏输入读取配对码，不写在命令历史里：

```powershell
.\.venv\Scripts\python.exe bridge/etf_agent_bridge.py --root E:\AI_Tools\Other\ETF-Agent-Bridge pair --origin "https://<你的站点域名>"
.\.venv\Scripts\python.exe bridge/etf_agent_bridge.py --root E:\AI_Tools\Other\ETF-Agent-Bridge doctor
.\.venv\Scripts\python.exe bridge/etf_agent_bridge.py --root E:\AI_Tools\Other\ETF-Agent-Bridge claim
```

设备只能领取、上传、心跳，不能发布报告或修改持仓/指标。只允许HTTPS（明确回环开发例外）；网页不会反向连接本机localhost。
`claim`只拉证据，不调用模型。手动研究结果需符合 `etf-research-result-v1`，可执行 `submit <job-id> <result-file>`。
Windows设备凭据以DPAPI保存；Linux0600仅是权限保护，不是加密。设备撤销/租约失效/取消后返回都被检查。

只有确实完成个人官方登录并检查版本/权限/额度后，才显式使用 `run-codex` 或 `work --max-jobs 1 --max-minutes 15 --model <已验证模型>`。
CLI当前审核版本门为0.149.0，不接受未知版本自动放宽。私有认证目录在Bridge根目录的 `runner-home/.codex`，不复制全局认证文件。
代码禁模型工具/自由联网；独立CODEX_HOME本身不等于操作系统沙箱，实际环境仍需权限测试。
本包不包含任何模型API Key配置通道。用户订阅和API额度不可互相假定；失效要停，不自动改用收费通道。

## 盘后任务和停止

`WORKSPACE_DAILY_REVIEW_ENABLED` 与用户个人 `daily_review` 都开启，且交易日历和收盘快照满足条件，worker才幂等创建候选研究任务。
它不会自行调用模型。真正运行由已配对、预算受限的Bridge负责，默认并发1。
本包没有创建系统计划任务。先验证单次任务/重复/断网/撤销，再自行决定是否设置定时；程序需离线显示最后成功日期，不能冒充今天。

## 发布/回滚必查

备份数据库和配置；独立分支审查/CI；确认迁移只有1个head；生产认证与HTTPS；真实行情时效/单位/复权；OCR可用性；图表与快照匹配；模型登录/费用；跨用户隔离。
关闭新UI开关可回旧壳，但不能直接删除已有工作站表。真实数据迁移先演练，不使用盲目reset或破坏性downgrade。
