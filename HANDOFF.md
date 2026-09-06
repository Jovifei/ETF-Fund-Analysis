# 交接说明（v0.8.x）

更新时间：2026-09-06  
应用发行版本：`0.8.0`  
产品/导航合同：`v0.8.1`

这份根目录文件只负责告诉后续 Agent **先读什么、不要做什么**。完整项目脉络已经迁移到 `docs/` 当前权威文档。

## 接手前阅读顺序

1. `AGENTS.md` — 安全、数据真实性、策略修改硬合同；
2. `STATUS.md` — 当前最短状态；
3. `docs/README.md` — 文档权威层级；
4. `docs/PROJECT_HANDOFF_20260906.md` — 最终目标、历史、开源借鉴、卡点；
5. `docs/UI_UX_CONTRACT.md` — 页面/颜色/组件/交互；
6. `docs/ROADMAP_TO_FINAL.md` — 剩余工作；
7. `docs/NAVIGATION_CONTRACT_V081.md` — 当前路由精确合同；
8. `docs/ARCHITECTURE.md`、`docs/IMPLEMENTATION_MATRIX.md`；
9. 修改专题代码前再读对应测试和专题文档。

## 当前用户工作流

```text
/               决策
/boards         板块
/holdings       持仓
/research       研究
/research/news  新闻
/system         系统
/decision/1430  决策的 14:30 二级模式
/etf/{code}     全局唯一 ETF 详情
```

旧 `/legacy`、`/workbench/*` 只做兼容。不要重新把它们放回一级导航。

## 当前最重要的语义合同

### 一个 current action
同一 ETF 同一时刻只能有一个 canonical current action：

```text
可加仓 / 可入场 / 可试探 / 观望 / 减仓
```

研究 score、Signal Center coefficient、14:30 排名分只能排序/解释，不能改写它。

### 一个 ETF 详情
从 Decision / Boards / Holdings / Research / 14:30 看单只 ETF 都去：

```text
/etf/{code}
```

### 一个 forecast horizon 合同

```text
1 / 3 / 5 / 10
```

20D 是历史规划/可选未来研究，不是当前运行合同。

未 calibrated 的 `p_up` 只能写“历史相似样本上涨占比”。

### 数据真实优先

- Mock/stale/degraded/unverified/missing 不冒充真实；
- 日 K 不冒充分钟线；
- provider 失败显示错误/降级，不恢复静态假数据；
- 所有外部数据经过 Provider Adapter + audit。

## 页面视觉合同

不要“凭印象重画”。读 `docs/UI_UX_CONTRACT.md`：

- WorkBuddy：信息优先级/五档分组/指标解释参考，不是像素级复制；
- `illusionno/fund-analysis-matrix`：暗色金融卡片/表格与详情交互参考；
- 中国行情习惯：上涨/偏强用红暖色，下跌用绿；风险/阻断另用清楚的状态强调，不与行情方向混淆；
- forecast 情景使用独立紫/虚线/非实际标识；
- 当前 Canvas 已有 zoom/pan/crosshair/Zone，不因旧计划提 Lightweight Charts 就强制重写。

## 生产浏览器认证与数据库合同

后续部署/排障文档必须继续明确下面这套浏览器数据库认证配置，不能恢复旧 Bearer Token/localStorage 方案：

```text
AUTH_ENABLED=true
DATABASE_URL=<PostgreSQL URL>
AUTO_CREATE_SCHEMA=false
AUTH_COOKIE_SECURE=true
```

数据库完成 Alembic 迁移后，在服务器本地使用：

```text
fund-decision auth-bootstrap-admin
```

创建首个管理员。浏览器只通过 HttpOnly/SameSite Cookie 会话与 CSRF 保护访问；密码、会话令牌和生产凭据不得写入 localStorage、页面、Git、聊天或报告。

## 当前真正卡点

功能很多已经实现，但**最终研究可信度还没封版**：

1. 真实 5/15m 14:30 point-in-time 数据；
2. 费用/滑点/可成交性/停牌涨跌停等事件约束；
3. 1/3/5/10 forecast OOS 校准；
4. 事件驱动验证；
5. Shadow Run；
6. 人工批准。

因此当前必须继续保持：

```text
historical_1430_backtest = not_qualified
```

这比继续增加指标、页面或模型更优先。

## UI 技术债

- `/holdings`、`/research`、`/system` 仍复用 legacy shell；
- `/decision/1430` 仍有独立 HTML/JS；
- 最终可拆组件和删除 legacy DOM，但不能改变 current action / forecast / 数据真实性合同。

## 每次修改流程

1. 读当前代码/测试，不从旧聊天/旧计划直接推断现状；
2. 先写失败测试或复现；
3. 修改；
4. 运行相关局部测试；
5. 跑完整 CI 门禁；
6. 策略/指标/预测语义改动必须升级相应版本并补 walk-forward/回测/泄漏检查；
7. PR 合并后再部署；
8. 生产先备份、`git pull --ff-only`、迁移、health/provider audit/smoke，可回滚。

## 不做

- 自动交易；
- 券商连接；
- AI 自动写 current action/持仓；
- 为了回测好看自动调阈值；
- 把测试/Mock/旧生产记录描述成当前新变更的生产证据；
- 从第三方源码/历史 Git/文档复制凭据或违反许可证。

如接下来没有用户新的优先级指示，默认按 `docs/ROADMAP_TO_FINAL.md` 的 P0 开始：**真实 14:30 point-in-time 数据闭环。**
