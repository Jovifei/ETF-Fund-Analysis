# v0.8.0 发布与更新记录 (Release Notes)

发布日期：2026-09-05  
发行版本：`v0.8.0`  
核心提交：`d7fac33f0b4b47f96ea54e7a605aba09b5731742` (branch: `main`)  
环境要求：Python >= 3.11, PostgreSQL >= 16 (Alembic head: `c2d3e4f5a6b7`), Docker Compose

---

## 一、 版本概述

`v0.8.0` 是本系统架构收敛与产品任务闭环的重大里程碑版本。本次更新彻底告别了过去按历史版本碎片化拼凑的 4 个平行网站形态，围绕个人投资者每个交易日 14:30 尾盘买卖判断的真实工作流，重构为 **4 个一级业务入口（🎯 决策总览 / 🔥 行业板块 / 💼 我的持仓 / 🔬 研究中心）** 与 **全系统统一的交互式 ETF 详情研判台（`/etf/{code}`）**。

同时，本次发布彻底排查并根除了历史积累的假数据回退、邀请码默认值、指标多处重复计算、支撑压力输入漂移等一系列技术债务与安全红线，所有计算引擎与数据展示全部收敛至单一口径权威。

---

## 二、 核心变更清单

### 1. P0 安全漏洞与数据真实性红线彻底根除
- **假数据静态回退完全销毁**：彻底移除 `kline_stabilization.js` 中 2026-08-31 静态假行情快照与回退分支；接口失败一律显示显式错误态并带重试，严禁假数据冒充实时；
- **注册安全加固（Fail-Closed）**：移除 `config.py` 中默认邀请码 `"etf2026"`，默认配置 `REGISTRATION_ENABLED=false` 且 `REGISTRATION_INVITE_CODE=None`；服务端未显式配置邀请码时直接关闭公开注册（返回 403）；
- **死代码清理与统一 Cookie 鉴权**：删除 `localStorage` 中旧 Bearer Token 残留死代码；全站统一采用 HttpOnly Cookie + CSRF 双令牌鉴权；按钮文案全面统合为“退出登录”。

### 2. 计算引擎唯一起点与指标口径归一
- **单一指标状态语义（Single-Source Indicator Semantics）**：
  - 新增 `app/utils/indicator_state.py`，作为全系统指标呈现状态（MA/MACD/KDJ/RSI/TD9/量能）的**唯一起点**；
  - `SignalGradeService`、`KlineStabilizationService` 与 `ETF1430WorkbenchService` 统一读取 `IndicatorSnapshot`，**彻底废除每次 HTTP 请求对全量历史 K 线的重复计算**；
  - 废除前端客户端二次打分（`decision_board_workbuddy.js:34-53`），以服务端 Python 计算为唯一权威。
- **支撑压力统一快照存储（Unified S/R Store）**：
  - 新建 Alembic 迁移 `a9b8c7d6e5f4` 增加 `support_resistance_snapshots` 存储表；
  - 统一切窗（250根）与真实成交额输入；`decision_board` 与 `etf_1430` 共用单一同源快照，两页支撑压力价位 100% 一致（新增 cross-surface 测试保护）；
  - 支撑压力升级为带上下界的半透明区域（Zone）；
  - 增加 `td9_cluster` 价格确认算法，利用历史上 TD9/TD13 反转 K 线的高低点聚类确认关键价格区间。
- **消除全表扫描与性能优化**：
  - 新增 `app/utils/latest_snapshots.py`，通过数据库窗口查询（Window/Group-Max）获取最新预测和信号，消除了 `CurrentDecisionService` 和 14:30 历史扫表性能债。

### 3. 产品信息架构收敛与全局 ETF 详情研判台
- **统一 App Shell 与命名**：
  - 根路径 `/` 统一命名为「ETF 决策 · 总览」；
  - 顶栏导航规范为 `🎯 决策 (/)` · `🔥 板块 (/boards)` · `🔬 研究中心 (/legacy)` · `⏱️ 14:30 尾盘 (/workbench/1430)`；
- **落地全局 ETF 详情研判台（`/etf/{ts_code}`）**：
  - 采用轻量专业金融图表引擎（纯本地自托管 Canvas 状态机，零外部 CDN 脚本，100% CSP 安全）；
  - 支持鼠标滚轮无级缩放、视口平移拖拽、双击复位、十字光标与浮动 OHLC 提示框；
  - 支撑压力半透明区域（Zone Layer）与指标过滤联动；
  - 叠加 TD9 变盘提示与未来预测情景走廊；
- **旧 K 线页面平稳退休**：
  - `/workbench/kline` 及其静态资源配置 307 重定向至 `/boards`（其研判功能已被 `/etf/{code}` 全面接管）；相关 API 标记 `deprecated=true`。

### 4. 用户自选 Watchlist 与持仓预测融合
- **用户自选解耦**：
  - 新建 Alembic 迁移 `b0c1d2e3f4a5` 增加 `user_watchlist_entries` 表；
  - 落地 `GET /api/watchlist`、`POST /api/watchlist/entries`、`DELETE /api/watchlist/entries/{id}`，普通用户输入 6 位代码自动识别并加自选，解耦全局 Universe 与个人关注；
- **持仓预测期限结构融合**：
  - `GET /api/holdings` 自动关联官方 action、1/3/5/10日预测及最近支撑压力；
  - 持仓页面新增“我的自选”面板及一键转持仓/看详情功能。

### 5. 一等行业板块市场与多周期分钟 K 线底座
- **行业板块市场（`/boards`）**：
  - 落地 `/boards` 页面与 `GET /api/sectors/market` 聚合接口，展示 266 个板块涨跌、上涨/下跌家数比、主导 ETF 代理与成分芯片；
- **多周期分钟 K 线底座（`market_bars`）**：
  - 新建 Alembic 迁移 `c2d3e4f5a6b7` 增加 `market_bars` 表（支持 30m/60m/1d）；增加 `MarketBarService` 与接口；日 K 坚决不冒充分钟线；
- **新闻分析分层呈现**：
  - 新闻卡片明确标注解读来源（“词典启发式（未启用 AI）” vs “模型分析 · <model>”），AI 解读置顶为主要分析，启发式标记为次要证据。

---

## 三、 发布质量门禁执行记录

在正式合并与发布前，全套质量门禁均已 100% 严格执行通过：

1. **Python 编译检查**：
   `python -m compileall -q backend/app` -> **0 错误**。
2. **前端 JS 语法检查**：
   `node --check` 检查 6 个主要前端脚本（`app.js`, `boards.js`, `decision_board_workbuddy.js`, `etf_1430_workbench.js`, `etf_detail.js`, `kline_stabilization.js`） -> **全部通过**。
3. **自动化回归测试套件**：
   `pytest -q` -> **`705 passed, 3 skipped, 0 failed`**。
4. **代码敏感凭据扫描**：
   全代码库扫描无任何硬编码 Token、密码、密钥。

---

## 四、 生产环境部署与数据迁移记录

- **代码同步**：`git merge --ff-only feat/repair-plan` 合并至 `main` 并推送到 GitHub 远端；生产服务器通过受审计更新包平滑同步至最新 HEAD；
- **数据库迁移**：成功在容器中执行 `alembic upgrade head`，应用了三项数据库升级：
  - `a3b4c5d6e7f8 -> a9b8c7d6e5f4` (`support_resistance_snapshots`)
  - `a9b8c7d6e5f4 -> b0c1d2e3f4a5` (`user_watchlist_entries`)
  - `b0c1d2e3f4a5 -> c2d3e4f5a6b7` (`market_bars`)
- **系统健康状态**：
  - API 容器：`china-fund-decision-api-1`（healthy，版本响应 `0.8.0`）
  - 调度容器：`china-fund-decision-scheduler-1`（running，30s 心跳正常）
  - 数据库容器：`china-fund-decision-db-1`（healthy）
- **路由实测状态**：
  - `GET /` -> 200 OK
  - `GET /boards` -> 200 OK
  - `GET /etf/512480.SH` -> 200 OK
  - `GET /legacy` -> 200 OK
  - `GET /workbench/1430` -> 200 OK
  - `GET /workbench/kline` -> 307 Temporary Redirect（至 `/boards`）
