# 生产部署收据（2026-11-15 UI/UX 全面重构）

## 一、发布概要与镜像元数据

- **发布时间**：2026-11-15 19:42 (UTC+8)
- **目标提交**：`342fa84861b5dd1dafe3fa5e9b7754f9a5d3f443`
- **代码分支**：`integrate/us-markets-20261114`（已成功推送至 GitHub 仓库）
- **发布镜像**：`china-fund-decision:deploy-342fa84`（Image ID: `c50ed78b3c84`，909MB）
- **生产服务**：
  - `etf-deploy-342fa84-api-1`：Up / `healthy` / 监听 `127.0.0.1:8080->8000/tcp`
  - `etf-deploy-342fa84-worker-1`：Up / `healthy`
  - `etf-deploy-342fa84-scheduler-1`：Up / 运行中
- **数据库状态**：Alembic 迁移 Head 保持 `b7c8d9e0f1a2`（零迁移，无 schema drift）
- **切流前备份**：
  - 备份文件：`/opt/china-fund-decision/backups/fund_pre_342fa84_cutover_20261115_193002.dump`（424MB）
  - 伴生校验：`fund_pre_342fa84_cutover_20261115_193002.dump.sha256`
  - TOC 校验：478 条条目完整验证
- **回滚准备**：
  - 前序容器 `etf-deploy-129840e-api-1`、`worker-1`、`scheduler-1` 完整保留（处于 stop 状态）
  - 前序镜像 `china-fund-decision:deploy-129840e` 保留，支持秒级回滚。

---

## 二、本次更新内容与功能特性

严格遵循《Agent 操作契约》，在 **零修改后端 API 接口、零改动评级体系与指标公式、保持全部原有功能** 的约束下，完成了 Web 端 UI/UX 的全面现代化改造：

1. **总览核心 34-ETF 决策矩阵首屏置顶 (`Overview.vue` / `OriginalDecisionBoard.vue`)**：
   - 将原先深埋在页面最下方的 34-ETF 决策看板提升至首屏（Top Fold），进入首页即直接研判。
   - 原生高性能 Vue 决策表格全面替换 iframe，消除双滚动条与通信延迟。
   - 增加 5 档评级筛选胶囊（全部、关注加仓、中性观察、减仓回避、数据异常）。
   - 增加快速搜索栏、1/3/7/20/60 天预测跨度切换、收藏标的（⭐）一键筛选。
   - 威科夫结构、道氏趋势、ATR 波动风险以彩色胶囊展示，悬浮呈现专业量化研判 Tooltip。
   - 保留切换回旧版 iframe 的兼容性开关。
   - 底部折叠收纳历史数据准备清单与离线重算运维工具。

2. **全局导航与顶栏合规展示 (`App.vue` / `style.css`)**：
   - 顶栏新增数据同步与 AI 状态指示胶囊，点击直达配置锚点。
   - 全局顶部收敛展示标准合规条：`[🛡️ 研究展示] · not_calibrated · actionable=false · 不连接券商 · 不自动下单 · v104`，消除各面板分散多余的警告框。
   - 侧边栏/主导航加入第一级 `美股研究` 入口。

3. **设置页 4 大分栏与 AI 抽屉交互 (`Settings.vue` / `AIProfileManager.vue`)**：
   - 将原先堆叠的 8 个长表单拆分为 4 大清晰 Tab：`👤 账户与偏好` (`#account`)、`🤖 AI 模型服务` (`#ai`)、`📡 数据与设备` (`#data`)、`🛡️ 系统管理` (`#system`)，支持 URL Hash 锚点直达。
   - AI 模型配置升级为 480px 侧滑抽屉（Slide-over Drawer），避免页面布局跳动。
   - 内置 DeepSeek、OpenAI、Kimi 官方预设一键填入配置。
   - 费用确认升级为 Switch 开关，测试按钮增加未满足条件时的悬浮说明。

4. **ETF 详情页降噪与 3 分栏重组 (`Detail.vue` / `IndicatorReadings.vue`)**：
   - 顶部 13 项紧密堆叠的数据快照元数据收纳进 `<details>` 折叠抽屉（`[ℹ 数据溯源与计算口径]`），净化视觉焦点。
   - 拆分为 3 大清晰 Tab：
     - `📈 技术图表与指标`（K线图 + 技术指标快照）
     - `🎯 未来情景预测`（预测情景面板）
     - `🤖 AI 研究与证据`（AI 研究报告与证据链）
   - 技术指标数值卡片升级为等宽数字（tabular-nums）与对比高亮卡片。

---

## 三、生产公网验证结果

- **公网地址**：`https://etf.joviluma.com/`
- **HTTP 状态**：`200 OK`
- **静态资源版本**：
  - `<script type="module" crossorigin src="/workspace-assets/index-l5IyPaof.js"></script>`
  - `<link rel="stylesheet" crossorigin href="/workspace-assets/index-ypKbE7zI.css">`
- **公网 API 健康检查 (`/api/health`)**：
  - 返回：`{"status":"ok","app":"ETF Fund Decision","version":"1.0.13","environment":"production","provider":"public_composite","auth_enabled":true}`
- **安全响应头**：
  - `Content-Security-Policy: default-src 'self'; ...`
  - `Strict-Transport-Security: max-age=31536000; includeSubDomains`
  - `X-Content-Type-Options: nosniff`
  - `X-Frame-Options: SAMEORIGIN`
- **未认证拦截守卫**：
  - `/api/workspace/holdings` -> `401 Unauthorized`
  - `/api/workspace/sectors/representatives` -> `401 Unauthorized`

---

## 四、秒级回滚演练路径

如需紧急回滚至前序版本，可在宿主机执行以下命令，旧版本容器将在数秒内恢复服务：

```bash
cd /opt/china-fund-decision/etf-deploy-342fa84
docker compose --env-file /opt/china-fund-decision/.env -f new.yml down
docker start etf-deploy-129840e-api-1 etf-deploy-129840e-worker-1 etf-deploy-129840e-scheduler-1
```
