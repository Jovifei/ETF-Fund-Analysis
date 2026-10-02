# 本地 Codex：接收、验证并合并 ETF 14:30 Workbench

将本文件全文交给本地 Codex。

---

你现在接收一个**完整仓库覆盖包**，其基础来自 GitHub `main`，并增加了真实的 ETF 14:30 Workbench 源码。不要再依赖远端空壳分支。

打包基线：

```text
42c7203022bb1f9e9716bffe73b44a4f134c1fc5
```

若执行时 `origin/main` 已前进，不要用完整包覆盖新提交；改用增量覆盖包并逐项审查冲突。

## 目标

1. 将压缩包中的文件覆盖到本地 `Jovifei/ETF-Fund-Analysis` 工作树；
2. 核对新增文件；
3. 运行完整门禁；
4. 在本地 Mock 浏览器验收；
5. 创建新分支并提交；
6. 推送功能分支；
7. 创建 PR；
8. PR/CI 全绿后合并到 `main`。

## 安全边界

- 不输出或提交 `.env`、Token、API Key、Cookie、数据库密码、账户号、公网 IP；
- Mock 不能冒充真实数据；
- 日线不能冒充 14:30 分钟 point-in-time 证据；
- 未来蜡烛是情景，不是实际未来 K 线；
- MACD/KDJ/RSI 只确认价格拐点，不直接产生价格；
- `chan_zone_approx` 不是完整缠论；
- 不自动交易、不连接券商、不创建订单；
- 不自动把 `not_calibrated` 改成 `calibrated`。

## 一、覆盖文件

假设解压目录为：

```text
/path/to/ETF-Fund-Analysis-etf-1430-complete/
```

本地仓库为：

```text
/path/to/ETF-Fund-Analysis/
```

先检查工作区：

```bash
cd /path/to/ETF-Fund-Analysis
git status --short
git fetch origin --prune --tags
git checkout main
git pull --ff-only origin main
```

如有用户未提交改动，停止，不要 reset/clean/stash。

然后覆盖：

```bash
rsync -a \
  --exclude='.git/' \
  --exclude='.env' \
  --exclude='.venv/' \
  --exclude='*.sqlite' \
  --exclude='*.sqlite3' \
  --exclude='reports/' \
  --exclude='backups/' \
  --exclude='reports/*.json' \
  --exclude='backups/*' \
  /path/to/ETF-Fund-Analysis-etf-1430-complete/ \
  /path/to/ETF-Fund-Analysis/
```

Windows 可使用解压后复制覆盖，但必须保留本地 `.git` 和 `.env`。

覆盖后读取并执行删除清单：

```bash
while IFS= read -r path; do
  [ -n "$path" ] && rm -f -- "$path"
done < WORKBENCH_DELETE_PATHS.txt
```

当前清单会删除旧的临时导出工作流：

```text
.github/workflows/export-etf-1430-workbench.yml
```

## 二、核对新增文件

必须存在：

```text
backend/app/api/workbench_1430.py
backend/app/services/etf_1430_service.py
backend/app/utils/support_resistance.py
backend/app/static/etf_1430_workbench.html
backend/app/static/etf_1430_workbench.css
backend/app/static/etf_1430_workbench.js
backend/tests/test_etf_1430_workbench.py
backend/tests/test_support_resistance.py
config/etf_1430_workbench.json
scripts/generate_1430_decision.py
scripts/run_1430_decision.sh
scripts/build_1430_point_in_time_dataset.py
deploy/systemd/etf-1430-decision.service
deploy/systemd/etf-1430-decision.timer
docs/ETF_1430_DECISION_WORKBENCH.md
docs/SUPPORT_RESISTANCE_SEMANTICS.md
docs/OPEN_SOURCE_1430_RESEARCH.md
docs/ETF_1430_VALIDATION.md
```

并确认 `backend/app/main.py` 包含：

```text
workbench_1430_router
/workbench/1430
```

## 三、创建功能分支

```bash
git checkout -b feat/etf-1430-workbench-complete-local
```

## 四、完整测试

使用 Python 3.12：

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e '.[dev,market]'

pytest -q
python -m compileall -q backend/app
node --check backend/app/static/app.js
node --check backend/app/static/etf_1430_workbench.js
python codex/skills/fund-research/scripts/check_no_secrets.py .
bash -n scripts/run_1430_decision.sh
python -m json.tool config/etf_1430_workbench.json >/dev/null
```

如有 ShellCheck：

```bash
shellcheck scripts/run_1430_decision.sh
```

不得删除测试或降低断言。

## 五、Mock 浏览器验收

```bash
export APP_ENV=development
export AUTH_ENABLED=false
export MARKET_PROVIDER=mock
export ALLOW_MOCK_FALLBACK=false
export DATABASE_URL=sqlite:///./etf1430-local.sqlite3
export REPORTS_DIR=./reports

fund-decision bootstrap --lookback-days 520
uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
```

打开：

```text
http://127.0.0.1:8000/workbench/1430
```

检查：

- 1/3/5/10 日预测；
- 点击 ETF 打开详情；
- 历史蜡烛和未来情景蜡烛分界；
- 未来区域标记“非实际结果”；
- 支撑/压力线；
- 综合、均线、MACD、KDJ、RSI、缠论近似、成交密集模式；
- Mock 时 `actionable=false`；
- `not_calibrated` 可见；
- 1440/1024/390 像素无严重重叠；
- 原主看板无回归。

## 六、point-in-time 数据脚本烟测

准备一个不含敏感信息的 5 分钟样例 CSV，并执行：

```bash
python scripts/build_1430_point_in_time_dataset.py \
  sample_5m.csv \
  --interval-minutes 5 \
  --cutoff 14:30 \
  --output deployment_reports/etf_1430_point_in_time_sample.json
```

确认：

- `feature_cutoff_verified=true`；
- 特征只使用 14:30 及之前记录；
- execution 使用 14:30 后第一条记录；
- 1/3/5/10 日标签与特征字段分离。

## 七、提交功能分支

```bash
git status --short
git diff --check
git add -A
git commit -m "feat: implement ETF 14:30 forecast and support-resistance workbench"
git push -u origin feat/etf-1430-workbench-complete-local
```

创建 PR 到 `main`。PR 必须说明真实环境仍未完成：

- Tushare/AKShare 权限；
- 真实 5/15 分钟历史；
- 14:30 point-in-time 回测；
- CZSC 完整缠论对账；
- PostgreSQL/ECS/systemd；
- 20 个交易日影子运行。

## 八、合并

只有本地门禁和 GitHub Actions 全绿后：

```bash
git checkout main
git pull --ff-only origin main
git merge --no-ff origin/feat/etf-1430-workbench-complete-local \
  -m "merge: ETF 14:30 forecast and support-resistance workbench"

pytest -q
python -m compileall -q backend/app
node --check backend/app/static/app.js
node --check backend/app/static/etf_1430_workbench.js
python codex/skills/fund-research/scripts/check_no_secrets.py .

git push origin main
```

等待 `main` CI 全绿。

## 九、本地交付报告

创建：

```text
deployment_reports/YYYY-MM-DD-etf-1430-local-merge.md
```

记录：覆盖包 SHA-256、分支、提交、测试、浏览器、API、point-in-time 脚本、PR、合并 SHA、CI 和未完成真实资格。不得记录任何凭据。
