# 启动和访问

先读 [STATUS](STATUS.md)，区分真实任务、隔离演示与公网展示。新版Vue入口不是旧8000端口静态界面。

## 正常网站

访问 https://etf.joviluma.com/ ，使用已有账户正常登录；核对批次、源时间、日线日期与过期提示。登录成功不等于数据消费通过。

## 隔离Vue演示：8081

在没有.env或deploy/.env.production的干净工作树执行；不要删除/搬走原配置。优先复用已有Python3.12及Node环境。

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
npm ci --ignore-scripts --prefix frontend
npm run build --prefix frontend
.\.venv\Scripts\python.exe scripts/run_workspace_demo.py --smoke
.\.venv\Scripts\python.exe scripts/run_workspace_demo.py --port 8081
```

访问 http://127.0.0.1:8081/ 和 http://127.0.0.1:8081/etf/512480.SH ，Ctrl+C停止前台服务。演示仅用Mock及隔离数据库，不采集真实行情或调用付费AI，不写正式账户/持仓。仅本地HTTP开发使用APP_ENV=development，生产不降低安全Cookie保护。

## 已有真实任务

数据根F:\ETF_Data\ETF-Fund-Analysis：db/research.sqlite3为研究库，state/schedule.sqlite3为调度台账，outbox保存包/回执。ETF-Local-Live-Compute调用固定源码，每分钟唤醒只在到期slot执行；不能并行启动旧/新控制器。检查时先只读核实Action、attempt/jobs、manifest/receipt与源日期。

停止正在运行任务可用 `Stop-ScheduledTask -TaskName 'ETF-Local-Live-Compute'`；停用计划应另有原因和恢复记录，不随文档清理执行。不伪造DELIVERED、延长旧包有效期或补造历史slot。

## 生产维护

保持AUTH_ENABLED=true、持久DATABASE_URL、AUTO_CREATE_SCHEMA=false、AUTH_COOKIE_SECURE=true；保留已有用户/持仓，首次用auth-bootstrap-admin初始化管理员，浏览器正常登录。

先备份、核精确源码/镜像、测试复审及回滚，再执行获准切换。`alembic current`、`alembic check`用于检查；`alembic upgrade head`仅用于获准迁移。本文不授权生产库写入、服务器备份清理或本机数据删除。详见 [部署手册](docs/ALIYUN_DEPLOYMENT.md)。
