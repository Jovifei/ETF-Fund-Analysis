# ETF Research 工作站：完整源码交付

交付日期：2026-09-06。正式发布版本：`1.0.1`。

这是完整项目源码包，不是只有 docs 的规划包，也不是需要另找原文件的增量补丁。
包含原有后端、旧界面、Vue 新界面、数据库迁移、测试、Bridge、Vibe 产物适配、部署文件及**已构建的前端**。
不包含 `.git`、真实数据库、真实持仓、认证文件、密钥、Python/Node 依赖目录或字体文件。
本次 ZIP 交付没有再推送或合并 GitHub；由 Jovi 自行提交。

## 先核验，再看界面

在新目录解压，不要覆盖正在使用的工程或生产配置：

```powershell
cd ETF-Fund-Analysis
python scripts/verify_delivery.py
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e "."
.\.venv\Scripts\python.exe scripts/run_workspace_demo.py
```

macOS/Linux 对应：

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/python scripts/run_workspace_demo.py
```

然后访问 `http://127.0.0.1:8081`。初次生成演示快照需要片刻；不需要模型登录或先安装 Node。
脚本只绑定回环地址，使用临时模拟数据库；界面持续显示演示标识。关闭进程后演示持仓不保留。
它拒绝在已有 `.env` / `deploy/.env.production` 的目录旁启动，不读取生产数据库。
真实持仓与真实行情请使用独立、有认证的部署，不能把无认证演示端口暴露到公网。

## 本地真实行情（v1.0.1）

先安装市场可选依赖，再只初始化 1–3 只 ETF 到仓库外的 SQLite 文件：

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[market]"
.\.venv\Scripts\python.exe scripts/initialize_local_market_data.py `
  --provider akshare `
  --codes 510300.SH 512480.SH 159928.SZ `
  --database-url "sqlite:///E:/Claude_allow/Download/etf-v101-runtime/market.sqlite3" `
  --report "E:/Claude_allow/Download/etf-v101-runtime/initialization-report.json"
```

这个命令执行 Alembic、走 `WorkspaceDataJob → TaskService` 的既有审计链，但不启动 scheduler、不调用模型、不接受 Mock，也不会从命令行读取或显示 Tushare Token。Tushare 要由运行环境或受控设置单独配置；先用 `/api/workspace/data-sources` 和 `scripts/qualify_market_data.py` 核验后再使用。

## 阅读顺序

1. [本轮实现、限制和验收](docs/DELIVERY_P0_P4.md)。
2. [当前测试报告](docs/TEST_REPORT_20260906.md)。
3. [本地/Docker 部署、Bridge 与 Vibe 接入](docs/LOCAL_WORKSPACE_DEPLOYMENT.md)。
4. [自行提交到 Git 的安全步骤](docs/SELF_SUBMIT.md)。
5. [planning-v2 唯一方案](docs/planning/WORKSPACE_PLANNING_V2.md)。

## 不应误解为已完成的事项

真实 Codex/Vibe 模型登录、真实上游完整研究、生产 Docker/PostgreSQL 与真实数据源联调尚未在本交付环境验收；标准 HTTP 浏览器端到端测试受当前受管浏览器访问策略限制。
已完成的离线浏览器验收与 ASGI 路由测试分别记录，不能替代上述证据。
历史 14:30 PIT、样本外校准、成交约束和长期 Shadow 仍需真实数据及时间积累，不因代码或截图完成而升级。
