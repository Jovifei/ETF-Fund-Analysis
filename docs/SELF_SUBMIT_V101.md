# 从已发布 v1.0.0 接收 v1.0.1

本版完整包用于独立运行/审查，增量补丁用于干净 Git 工作树。不要将整个 ZIP 镜像覆盖现有工程，尤其不要覆盖 `.env`、数据库、持仓、Codex 登录目录或别的 Agent 改动。

## 建议：用增量补丁保留正确父提交

```powershell
git clone https://github.com/Jovifei/ETF-Fund-Analysis.git ETF-Fund-Analysis-v101
cd ETF-Fund-Analysis-v101
git fetch origin codex/v1.0.0
git switch -c codex/v1.0.1 9a0ca1812eda24acc390f1b3097662bfd615dfef
git status --short
# 最后一行必须为空；将下面路径替换为收到的 patch 文件
git apply --check "E:\Downloads\ETF-Fund-Analysis_v1.0.0_to_v1.0.1.patch"
git apply "E:\Downloads\ETF-Fund-Analysis_v1.0.0_to_v1.0.1.patch"
```

不要先拉旧 main 再以为它等于 v1.0.0。若 v1.0.0 分支已产生新提交，以上 SHA 仍是补丁的精确基线；先比较新增改动再合并，不强制覆盖。

## 验证再提交

安装 Python 3.12 和 Node 22.18+，执行：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev,market]"
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m compileall -q backend/app scripts
npm ci --prefix frontend
npm run test --prefix frontend
npm run typecheck --prefix frontend
npm run build --prefix frontend
node --test backend/app/static/decision_board_workbuddy.test.js backend/app/static/legacy_route.test.js
git diff --check
.\.venv\Scripts\python.exe codex/skills/fund-research/scripts/check_no_secrets.py
git add -A
git diff --cached --stat
git diff --cached --check
# 人工核对 staged 内容，不含任何私人配置或运行数据，再执行：
git commit -m "feat(v1.0.1): wire bounded data providers and preserve ETF indicator matrix"
git push -u origin codex/v1.0.1-data-access
```

本次实际接收使用 `codex/v1.0.1-data-access`，父提交为 `9a0ca181`，提交 `224b59f` 已推送；未覆盖已有 `codex/v1.0.1`，未移动 v1.0.1 标签/Release，未修改 main。命令行 `gh` 未登录，因此 PR 创建链接为 [GitHub PR 页面](https://github.com/Jovifei/ETF-Fund-Analysis/pull/new/codex/v1.0.1-data-access)，需由已登录的仓库维护者提交。

`backend/app/workspace_dist/` 随完整包提供，Git 按原规则忽略。增量补丁不携带构建产物；CI/Docker 从锁文件构建。`PACKAGE_MANIFEST_V101.json` 证明完整 ZIP，不需要强行提交到 Git 后假装后续构建未改动文件。

本补丁保留现有 CI，新增标准浏览器用例和只读公共数据探测 workflow。公共探测 workflow 默认仅在指定功能分支的相关变更上执行；从别的分支接收后需按自己的 CI 审核规则调整触发范围，不能据此假称已运行。

## 部署/回滚

本版没有新增 Schema，head 仍为 d40609090002。真实数据部署前先备份与演练；旧单位日线只有完整重抓覆盖全部旧键才替换。
一旦替换了单位，回退到 v1.0.0 时不能只回退代码并继续使用新单位数据库；应恢复升级前完整备份或保留 v1.0.1 数据层。
云端测试通过不等于 Provider 已获资格；本次已在 `aliyun-etf` 维护窗口完成 v1.0.1 镜像/API/worker 部署和 health/HTTPS 验收，但仍不自动登录账户、不配置密钥、不启动计划任务、不升级研究资格。生产回滚细节见 [部署收据](DEPLOYMENT_RECEIPT_V101_20260907.md)。
