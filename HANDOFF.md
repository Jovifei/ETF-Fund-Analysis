# Agent交接：ETF研究工作站vNext规划

2026-09-06；代码基线 `3c7bdc7ff36b3dea482651e087127a33c4974903`；应用0.8.0，现有导航v0.8.1。**本轮只有文档，不代表新界面/研究器已上线。**

先读 `AGENTS.md` → `STATUS.md` → `docs/README.md` → `docs/planning/ETF_WORKSPACE_VNEXT.md`，再按模块读UI、开源审阅、桥接与因子治理。

最新目标：Kairo式左侧导航、顶部ETF搜索、底部个人账户；全市场总览、单ETF数据看板、可选AI、个人持仓导入/OCR与成本线、因子研究；本地Codex/Vibe结果经审核进入网站。低频主观判断、ETF先、个股后。旧“四入口冻结”“验证全部完成前不做UI”不再是排期合同。

当前授权仅研究和规划。下一步实施需用户批准；不要因为方案含M1–M6就立即安装、运行、定时或交易。产品目标来自最新需求；代码/测试证明当前实现，不证明需求已取消。

## 不能破坏的边界

唯一current action、IndicatorSnapshot、ForecastSnapshot、SupportResistanceSnapshot；1/3/5/10当前运行期限；未校准预测诚实标注；日K不冒充分钟K；个人数据隔离；外部AI不改策略/持仓/行情/权威动作；不接券商、不自动交易。现有生产模型无Shell/任意网络/写库工具，本地研究器工具权限另行ADR批准。

## 生产浏览器认证（保留部署交接合同）

```text
AUTH_ENABLED=true
DATABASE_URL=<PostgreSQL URL>
AUTO_CREATE_SCHEMA=false
AUTH_COOKIE_SECURE=true
```

迁移后仅在服务器本地使用 `fund-decision auth-bootstrap-admin` 创建首个管理员。浏览器使用HttpOnly/SameSite Cookie与CSRF；不恢复localStorage Bearer，不提交Token/Cookie/密码。先备份、通过测试、`git pull --ff-only`、迁移、health/audit/smoke并可回滚。当前任务不授权生产部署。

每次变更记录需求ID、SHA、来源、测试及范围、未完成项、回滚。上游源码/Skill先审阅许可证与权限，不复制全局配置；本地研究上传从手动研究包开始。
