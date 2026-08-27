# 隔离的上游参考源码

本目录只保存调研清单。`vendor/src/` 不进入 Git、Docker build context 或 Python path。

默认只拉取许可证清晰、已固定 revision 的参考仓库：

```bash
./scripts/fetch_reference_sources.sh
```

个人私用并已自行阅读上游 `LICENSE` / `COPYRIGHT` 后，可显式拉取标记为 `personal_use_fetch=true` 的项目：

```bash
./scripts/fetch_reference_sources.sh --include-personal-use
```

这只是“允许脚本下载到隔离目录”，并不把上游代码并入本项目，也不免除署名、许可证、商业条款、数据条款或禁止再分发等义务。

`zhangsensen/etf-rotation-strategy` 在本次审查的最新提交中记录了历史硬编码凭据和未清理的历史快照风险，因此 helper **始终阻止自动克隆**；只通过 GitHub 阅读必要文件并重新实现设计。
