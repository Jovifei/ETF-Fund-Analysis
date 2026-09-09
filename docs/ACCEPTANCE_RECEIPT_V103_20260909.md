# v1.0.3 远端代码验收收据

记录日期：2026-09-09。本收据只描述代码及隔离测试，不是用户电脑或生产部署收据。

## 固定接收对象

- 仓库：Jovifei/ETF-Fund-Analysis
- 基线：204a31cbc0214a6e80389224c238bc897b2279af
- 修复分支：fix/v103-history-research-20260909
- PR：https://github.com/Jovifei/ETF-Fund-Analysis/pull/31
- **已验收应用提交：9439563dafc35d7410f9dde39253478a321c96ef**
- 本收据与接收Prompt是该提交之后的纯文档补充，不改变运行代码SHA。未合并main、未改标签、未执行生产部署。

## 最终云端结果

| 流水线 | 固定head | 状态 | 记录 |
|---|---|---|---|
| ci #541 | 9439563d | success | https://github.com/Jovifei/ETF-Fund-Analysis/actions/runs/34300793218 |
| workspace-ci #64 | 9439563d | success | https://github.com/Jovifei/ETF-Fund-Analysis/actions/runs/34300793243 |

完整CI的job 102307061219于2026-09-09T01:57:21Z完成。全量pytest、Python编译、旧JS语法及单测、密钥扫描、干净数据库Alembic、ShellCheck、Compose、生产镜像构建与容器smoke全部成功。843项测试中的PostgreSQL条件单测未配置TEST_POSTGRES_URL而跳过，不能与容器中的PG迁移/启动smoke混为一项验证。

工作站CI包含24项Vitest、类型检查、生产构建、依赖高危扫描，以及11项普通真实HTTP Chromium用例和1项独立认证旅程。普通与认证旅程使用隔离Mock市场数据和测试账户；真实浏览器不等于真实行情已经接入。原模板、指数蜡烛图、收藏、人工复盘和账户流程纳入测试。

早期b0e5f82b的完整CI因根HANDOFF遗漏显式认证部署键失败；9439563d恢复了文档合同，保留测试并全量复跑成功。[过程记录](VALIDATION_V103.md)保留当时失败事实，本收据关闭该项，不把旧失败抹掉或拿旧绿色构建冒充当前结果。

## 分阶段应用提交

- aabc390c：逐标的历史隔离与价格指标展示。
- cec11c6b：实际指数OHLC缓存、三处收藏、历史补齐、人工复盘、因子选择、AI/OCR引导及市场归档。
- 4bb08a77：恢复独立、有时间依据的盘中研究状态。
- 0ecbad7d：缓存重算不依赖外部SDK/Token，首次指数任务初始化注册表。
- 9439563d：最终认证交接合同修正与证据整理。应用版本1.0.3；数据契约与正式期限未擅自升级。

## 本地必须补验，而非重新制作页面

按[固定接收Prompt](CODEX_RECEIVE_V103.md)及[详细L1–L5](LOCAL_ACCEPTANCE_V103.md)执行：原持久库备份/副本演练、真实ETF与三指数下载、行业/概念/目录覆盖、重启与断网缓存、收藏回流、可选OCR实际模型、本人Codex/Vibe官方登录和有预算单次报告、人工复盘与因子诊断。需要本人凭据或本地网络的结果不得由Mock代替。

本轮没有执行真实市场账户调用、用户服务器空间测量、实际OCR模型或真实模型研究。网站API Key安全Secret Store、行情包可信重导入/自动双向同步、一个月预测及自动反馈训练仍是未实现功能，不是打开某个开关即可完成。q code具体产品未确认。

[历史存储合同](HISTORY_STORAGE_V103.md) · [开源源码与吸收落点](OSS_APPLIED_V103.md) · [版本记录](versions/V1.0.3.md)
