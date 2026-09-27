# R2–R4A 路由与页面状态验收矩阵 — 2026-09-26

## 验收范围

路由来源是 `frontend/src/routerFactory.ts`，直达 Vue 的服务端白名单位于 `backend/app/workspace/ui.py`。浏览器验收运行在项目测试配置下，使用短生命周期 Mock 行情、虚构账户及临时 SQLite；它证明本地页面和流程，不证明生产账户或真实行情资格。

最终浏览器命令在项目配置上顺序运行，`retries=0`：普通 `20/20`、认证 `5/5`、响应式 `18/18`。全部通过。全部普通页面和旧入口也由新增 `frontend/e2e/route-matrix.spec.ts` 核对标题或重定向目标。

## 页面入口

| 页面/路径 | 预期页面 | 本次验证 |
|---|---|---|
| `/` | 市场总览 | `workspace.spec.ts`、`home-v102.spec.ts`：总览/板块/目录/搜索流程 |
| `/analysis`、`/etf/:code` | ETF 目录与统一详情 | 目录、图表、搜索导航；详情同读时刷新；空历史、无预测、禁用目录项和模块失败有前后端回归 |
| `/watchlist`、`/holdings` | 自选、持仓 | 收藏与持仓候选/确认/撤销流程；账户隔离由原有认证套件覆盖 |
| `/research/news`、`/factors` | 新闻、因子 | `workspace-v104.spec.ts` 的新闻年龄/因子说明及对应页面入口 |
| `/ai`、`/history`、`/review` | AI 研究、研究档案、每日复盘 | 路由入口通过；AI/人工审核流程在现有 E2E 中验证，未连接真实模型 |
| `/settings` | 设置与连接 | 数据诊断、连接步骤和不触发模型调用的流程通过 |
| `/profile`、`/login`、`/register` | 个人中心、身份入口 | 认证 E2E 使用测试数据库中的虚构账户；Mock 未认证环境下登录/注册入口按 session guard 返回总览 |

详情页状态有独立覆盖：已有价格但没有决策/预测、无历史准备、目录禁用、报价已过期、图表请求失败、详情后台刷新失败以及 401/404/500/超时文案。已保存数据在单模块失败时保留；历史准备只有用户显式点击后才创建任务。

## 旧路径及 404

| 旧路径 | 目标 |
|---|---|
| `/boards` | `/#market-boards` |
| `/decision/1430` | `/?mode=1430#etf-decisions` |
| `/matrix`、`/classic/etf-board` | `/#etf-decisions` |
| `/research`、`/legacy` | `/history` |
| `/system` | `/settings` |
| `/workbench/1430` | `/?mode=1430#etf-decisions` |
| `/workbench/kline` | `/analysis` |
| `/#holdings`、`/#news`、`/#system`、`/#signals`、`/#watchlist` | 对应 Vue 主页面 |

上述重定向由 route matrix 在普通 Mock 浏览器中逐条实测。UI 使用精确路径白名单，不把任意未知 URL 回退到首页；未知 API 与静态资源仍返回 404。直接访问任意未列出的网页路径可能由服务端返回 404，而不会加载 Vue 的客户端 `NotFound` 组件，这是当前 exact-route 服务合同。

## 状态覆盖边界

- 每条当前页面路由和表内重定向均已验证可到达预期路径/title。
- 详情空态、失败态、disabled 状态覆盖了新增状态合同；认证边界由虚构账户的 auth E2E 覆盖。
- 并非新闻、因子、档案等每个页面都对每种 HTTP 故障注入了一遍；其路由/核心流程通过本地 E2E，生产登录态页面仍未验收。
- 不涉及真人账户、自选持仓、线上数据、Provider 请求或生产部署。
