# 应用 ETF 14:30 Workbench 覆盖包

本仓库快照基于 GitHub `Jovifei/ETF-Fund-Analysis` 当前 `main` 的代码树构建，并增加 ETF 14:30 Workbench。基线提交为：

```text
42c7203022bb1f9e9716bffe73b44a4f134c1fc5
```

该提交与打包所用源码具有相同代码树；临时源码导出工作流不包含在包中。

## 推荐：使用完整仓库包覆盖现有工作树

先确保本地无未提交修改：

```bash
git status --short
git fetch origin --prune --tags
git checkout main
git pull --ff-only origin main
```

发现未提交修改时停止，不要执行 `reset --hard`、`clean` 或自动 `stash`。

假设完整包解压到：

```text
/path/to/ETF-Fund-Analysis-etf-1430-complete/
```

本地仓库为：

```text
/path/to/ETF-Fund-Analysis/
```

Linux/macOS：

```bash
rsync -a \
  --exclude='.git/' \
  --exclude='.env' \
  --exclude='.venv/' \
  --exclude='*.sqlite' \
  --exclude='*.sqlite3' \
  --exclude='reports/' \
  --exclude='backups/' \
  /path/to/ETF-Fund-Analysis-etf-1430-complete/ \
  /path/to/ETF-Fund-Analysis/
```

Windows：解压后复制全部文件到仓库根目录并选择覆盖，但必须保留本地 `.git`、`.env`、数据库、运行时报告和虚拟环境。

然后创建分支：

```bash
git checkout -b feat/etf-1430-workbench-complete-local
```

## 也可使用增量覆盖包

增量包只包含 `WORKBENCH_PATCH_FILES.txt` 中列出的新增/修改文件。将其根目录覆盖到本地仓库根目录即可。覆盖后按 `WORKBENCH_DELETE_PATHS.txt` 删除废弃文件；当前需要删除旧的 `.github/workflows/export-etf-1430-workbench.yml`。

## 必须执行的门禁

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e '.[dev,market]'

pytest -q
python -m compileall -q backend/app scripts
node --check backend/app/static/app.js
node --check backend/app/static/etf_1430_workbench.js
python codex/skills/fund-research/scripts/check_no_secrets.py .
bash -n scripts/run_1430_decision.sh
python -m json.tool config/etf_1430_workbench.json >/dev/null
```

完整执行流程见：

```text
docs/LOCAL_AGENT_PROMPT_ETF_1430.md
```

## 提交与推送

测试和本地浏览器验收通过后：

```bash
git add -A
git commit -m "feat: add ETF 14:30 forecast and support-resistance workbench"
git push -u origin feat/etf-1430-workbench-complete-local
```

创建 PR，等待 CI 全绿后再合并 `main`。不要直接强推 `main`。
