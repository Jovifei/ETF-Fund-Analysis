# 将完整交付包自行提交到远端

本次不替用户push/merge。ZIP不含Git历史或私有配置，建议使用**新克隆目录**提交，避免覆盖原工作树。

1. 解压到新的交付目录，先运行 `python scripts/verify_delivery.py`。
2. 另建干净Git克隆，检查 main。核对时 main 是 `3c7bdc7ff36b3dea482651e087127a33c4974903`；若已有新提交，不整包覆盖，先比较/合并。
3. 在新克隆创建 `feat/workspace-p0-p4-delivery`，把交付包中清单列出的源码、docs、配置示例、CI和测试复制到克隆。**不能复制 `.git`，不能删除或覆盖任何真实配置/数据库/持仓**。本包没有这些私有文件。
4. 删除下述已废弃的一次性自动补丁文件（仅在目标分支存在时）：
   `.github/workflows/workspace-finalize.yml`、`scripts/workspace-final-edits.json`。它们不应在新提交后再次自动改代码/提交。
5. 运行检查、审查diff，再手动提交和推送新分支。

```bash
git clone https://github.com/Jovifei/ETF-Fund-Analysis.git ETF-Fund-Analysis-submit
cd ETF-Fund-Analysis-submit
git rev-parse HEAD
git status --short
git switch -c feat/workspace-p0-p4-delivery
# 完成上述清单复制/两项废弃文件处理后：
git add -A
git diff --cached --check
git diff --cached --stat
python codex/skills/fund-research/scripts/check_no_secrets.py
# 人工确认 staged 文件均为源码/公开配置/文档，不含任何私人数据后：
git commit -m "feat: deliver ETF workspace P0-P4 with verified UI and research bridge"
git push -u origin feat/workspace-p0-p4-delivery
```

不要使用 `git reset --hard`、`git clean -fdx` 或 `robocopy /MIR` 清理现有工程；不要直接push main。
`backend/app/workspace_dist/` 是随包提供的构建产物，Git默认忽略；Docker/CI会从锁文件重建，无须强制入Git。
`evidence/` 是本次模拟验收截图/报告，可以审阅后提交；不包含用户真实资金信息。
根 `DELIVERY_MANIFEST.json` 证明本次原始ZIP文件清单。提交后修改源码或重新构建会改变校验结果，这是预期行为，不应改清单伪装未修改。

PR #26/#27/#28 保留为历史规划/开发参考；本包含对PR28的额外修复。不要又套用一次性 `workspace-final-edits.json`。
