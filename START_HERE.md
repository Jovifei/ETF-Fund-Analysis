# v1.0.1 后端数据接入与原 ETF 面板：接收入口

交付日期：2026-09-07（Asia/Shanghai）。应用/工作站版本：1.0.1。
基线是 **codex/v1.0.0 / 9a0ca1812eda24acc390f1b3097662bfd615dfef**，不是仍停留在旧版的 main。
本包包含完整源码、数据库迁移、测试、已构建 Vue 前端和第三方许可；不含凭据、真实数据库、持仓、Git 历史、依赖目录或字体。

**这是 v1.0.1 代码交付与部署入口；它不代表已创建 GitHub v1.0.1 标签或 Release。**
应用已推送到 `codex/v1.0.1-data-access` 并通过 CI；远端生产已完成镜像/API/worker 切换。用户 Windows 的 8081 Mock demo 仍与正式站点分开。

## 第一步：不要覆盖旧工程

在新目录解压并运行：

```powershell
python scripts/verify_delivery.py
```

该命令检查 `PACKAGE_MANIFEST_V101.json`，不安装、不联网、不读数据库。
原 `DELIVERY_MANIFEST.json` 仅保留原 P0–P4 ZIP 的历史清单；修改文件、重新构建或自行提交后不应继续用旧清单证明工作树未变化。

## 第二步：这次要真实数据，不要继续跑 demo

先读 [DATA_ACCESS_V101.md](docs/DATA_ACCESS_V101.md)。安装 Python 3.12 与市场依赖，把配置放在仓库外本人私有目录，选择 `composite`（本人 Tushare Token）或 `public_composite`（公开源）。Token 不提交、不粘贴聊天、不找历史 Git 凭据。
本包已带构建前端，单纯启动不用 Node；自行改前端/从 Git 部署时需 Node 22.18+、`npm ci` 和 build。

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[market]"
# 先将 deploy/workspace.live.env.example 复制到仓库外私有目录并由本人填写配置
.\.venv\Scripts\python.exe scripts/run_workspace_live.py init --config E:\ETF-Private\workspace.env --data-dir E:\ETF-Private\data
.\.venv\Scripts\python.exe scripts/run_workspace_live.py bootstrap-admin --config E:\ETF-Private\workspace.env --data-dir E:\ETF-Private\data
.\.venv\Scripts\python.exe scripts/run_workspace_live.py serve --config E:\ETF-Private\workspace.env --data-dir E:\ETF-Private\data --port 8082
```

路径是可替换的例子。`init` 拒绝覆盖已有数据库；密码隐藏输入；serve 只监听 `127.0.0.1`，不自动采集或调用模型。停止保留数据。
浏览器打开 `http://127.0.0.1:8082/` 登录，在设置页查看“后端数据接入”，点击“更新跟踪池行情”；目录、新闻、板块、分钟线为独立任务。先少量 ETF 验证，不开启全市场高频循环。

`python scripts/run_workspace_demo.py` 的 8081 仍是临时 Mock 界面演示，不能用它替代以上持久数据服务。

## 面板入口

- `/matrix`：Vue 左栏内完整 ETF 指标总表。
- `/classic/etf-board`：原版 WorkBuddy 风格 ETF 密集五档面板，保留原 HTML/CSS/JS。
- 两者点击 ETF 都进入 `/etf/{ts_code}`，只读同一决策快照。

## 阅读与交接

[发布/部署审核](docs/V100_DEPLOYMENT_AUDIT_20260907.md) → [本版记录](docs/versions/V1.0.1.md) → [接入和启动](docs/DATA_ACCESS_V101.md) → [本版验证](docs/VALIDATION_V101.md) → [自行提交](docs/SELF_SUBMIT_V101.md)。
旧交付说明在 `docs/archive/release-v1.0.0/`；旧测试报告证明旧版，不替代本版测试。
