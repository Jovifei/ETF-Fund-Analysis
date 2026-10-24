# 进度和证据维护

PROJECT_MASTER_ROADMAP.md记录稳定产品路线；PROJECT_PROGRESS.json为唯一可编辑阶段台账；PROJECT_PROGRESS.md/.html由scripts/update_project_progress.py生成，禁止手改生成结果。

## 更新规则

1. 按当前固定源码、实际测试/运行/部署/用户证据更新状态、next_task、blockers和events，保留日期/身份及NOT_RUN原因。
2. S0–S9及子任务的code/tests/review/deploy/live五维分别验收；PASS绑定证据，N/A有范围原因。不因CI、health200、单包accepted、后续文档提交或旧基线通过而晋升。
3. 正式分母/退出条件未冻结前，不显示全项目完成百分比。历史iteration71的9/13保留为历史发布清单，不代表当前候选或全项目。
4. 按需生成和检查，JSON及生成结果同批提交：

```powershell
python scripts/update_project_progress.py
python scripts/update_project_progress.py --check
```

当前source、实际deployed source/image/schema、测试源码和文档HEAD分开记录。未读取生产身份时明确未核验，不把旧63c426a/9fe或版本标签当今天的事实。数据资格UNKNOWN、actionable=false、not_calibrated、无自动交易保持。

## 运行和权限

旧R10同次私有GET的零副作用核验只在相应读取合同验收中使用；不以登录前后计数或不同快照替代，不对普通文档/样式清理重复写生产库。自然两交易日和手机证据独立。

每次先保护原目录用户修改；在独立分支完成审查后，仅按实际授权合并/同步，不能无条件覆盖原目录文档。生成文件不能替代源码/发布收据。Hub上报遵守AGENTS，连接失败保留待发送状态、不伪造成功。

有范围或资格取舍时由Jovi决策；ChatGPT协作连接不可用要明确报告，继续独立可做的已授权工作，不冒称远端已复审。
