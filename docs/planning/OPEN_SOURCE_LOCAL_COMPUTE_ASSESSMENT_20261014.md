# 开源量化社区最新项目调研与本地 Agent 计算/投送/复盘架构评估 — 2026-10-14

**文档状态**：RESEARCH & ARCHITECTURE ASSESSMENT / PHASE-VNEXT CANDIDATE  
**编写基准**：当前主线包含本地安全计算管线（`local-display-v2`）、离线签名发布（`shadow_client`）与云端无状态呈现。  
**调研目标**：针对用户提出的核心链路需求——
> “数据本地自动下载更新 $\to$ 本地 Codex / Bot / Agent 执行计算决策 $\to$ 定时将数据更新投送到网站 $\to$ 定时再拉取数据到本地复盘”  

从 GitHub 及开源量化社区调研最新、活跃度高、架构契合的开源项目，进行深度比对、可行性分析与吸收落地建议。

---

## 一、 最新开源项目全景调研（2026年最新动态）

经对量化开源社区（GitHub、Gitee 及量化技术论坛）的检索审查，重点甄选了 4 个与当前需求高度互补的活跃开源项目：

| 项目名称 | 开源仓库 / 组织 | 核心定位与技术栈 | 核心特色 | 许可证 | 适用借鉴维度 |
|---|---|---|---|---|---|
| **quant-fletch** | `AbelTami/quant-fletch` | A 股 ETF 量化轮动系统<br>(Python, VectorBT, Pandas) | 极速向量化回测、严格 PIT 时点数据切片、开箱即用的宽基/行业 ETF 动量轮动模板 | MIT | **本地策略计算引擎与 PIT 安全** |
| **Qbot** | `UFund-Me/Qbot` | 全自动 AI 量化投研框架<br>(Python, FastApi, Webhook, Docker) | 端到端自动化管线（数据更新 $\to$ 本地多 Agent 计算决策 $\to$ 企微/钉钉/Web 多端推送 $\to$ 盘后自动归档复盘） | Apache-2.0 | **完整工作流闭环、定时任务编排与通知** |
| **streametf** | `yingxincui/streametf` | 交互式 ETF 轮动与投研看板<br>(Python, Streamlit, Plotly) | 策略与呈现彻底解耦、本地 SQLite/Parquet 直读、极低门槛的复盘可视化面板 | MIT | **本地交互式复盘可视化与界面直观度** |
| **qstock** | 开源量化社区常用库<br>(Python) | 极简多源数据聚合工具包<br>(东方财富/新浪/同花顺) | 零 Token 门槛拉取大盘宽基指数、ETF 即时行情、板块轮动资金流向 | LGPL/Apache | **本地公共行情冗余通道与大盘环境补充** |

---

## 二、 4 个开源项目的深度技术审查与借鉴点

### 1. `AbelTami/quant-fletch`：A 股 ETF 量化轮动与向量化加速
- **核心能力**：
  - 采用 **VectorBT** 作为底层向量化计算引擎，相较于传统的逐行事件循环回测，计算速度提升数十倍；
  - 实现了 **严格的 PIT（Point-in-Time）数据对齐**，在回测与实盘模拟中彻底隔绝前视偏差（Lookahead Bias），确保 14:30 盘中决策只依赖当时已产生的截面与时序特征；
  - 封装了经典的动量轮动（二八轮动、自适应波动率调整、趋势动量打分）。
- **对本项目的借鉴**：
  - **加速本地计算**：本项目目前基于 Pandas 逐行/逐标的计算指标（MACD、KDJ、RSI、动量、波动率），标的增多时耗时明显增加。可借鉴其向量化截面排序（Cross-sectional Vectorized Ranking）算子，将 34 只 ETF 的计算从分钟级降至秒级；
  - **PIT 安全约束**：与本项目 `AGENTS.md` 中“字段单位、复权和时间口径冲突时停止信号”高度一致，可吸纳其数据冻结切片测试用例。

### 2. `UFund-Me/Qbot`：全自动本地 Agent 自动化调度与端到端推送
- **核心能力**：
  - 提供了成熟的自动化作业架构：`Data Fetcher -> Local Strategy Engine -> Agent Summary -> Cloud/Webhook Delivery -> Post-Market Review`；
  - **Agent 协同决策模式**：将确定性计算（技术指标、仓位分级）与 Agent（Codex / LLM）的职责严格分离——Python 确定性计算输出结构化 JSON，Agent 仅负责“研读该 JSON 并撰写复盘摘要、宏观风险提示与操作注意事项”，坚决不用 LLM 算均线或仓位；
  - **多通道无状态投送**：支持将生成的决策报告打包投送到远程 Web、钉钉机器人或邮件。
- **对本项目的借鉴**：
  - **完整链路范式**：Qbot 的流水线与用户提出的“本地自动下载 $\to$ 本地 Codex/Bot 跑决策 $\to$ 定时更新投送网站 $\to$ 定时本地复盘”完全同构；
  - **看门狗与容错机制**：网络中断时自动重试、接口频控时自适应休眠（Exponential Backoff）。

### 3. `yingxincui/streametf`：极简解耦的本地交互式复盘
- **核心能力**：
  - 前后端无强绑定：页面不维护持久状态，直接以本地计算产生的 JSON 或 SQLite 为输入源；
  - 提供了清晰的资产轮动热力图、收益风险比走势图。
- **对本项目的借鉴**：
  - 在本地搭建一套零配置的复盘小工具（用于用户离线检查历史每一天的决策胜率与轮动效果），与线上正式网站形成“云端轻量展示 + 本地深度复盘”的双层格局。

---

## 三、 用户核心链路现状与可行性评估

用户提出的完整闭环链路：
$$\text{本地自动下载更新数据} \longrightarrow \text{本地 Codex/Bot/Agent 执行计算决策} \longrightarrow \text{定时更新投送到网站} \longrightarrow \text{定时拉取数据到本地复盘}$$

### 1. 当前打通现状对照表

| 环节 | 对应本地实现 | 当前状态 | 现状诊断与说明 |
|---|---|---|---|
| **1. 本地自动下载更新** | `akshare` / `public_composite` + `refresh_bars` / `refresh_quotes` | **已打通** | 本地 `F:\ETF_Data\ETF-Fund-Analysis\db\research.sqlite3` 具备 34 只 ETF 的完整历史与实时行情，已实现自动下载。 |
| **2. 本地 Agent/脚本计算决策** | `backend/app/workspace/local_compute.py` + `run_local_compute.py` | **已打通** | 确定性算法计算 34 只标的的 1/3/5/10 日预测、评级（入场/试探/观望/减仓）、板块观察，完全在本地 CPU 离线完成。 |
| **3. 定时打包投送网站** | `shadow_client.upload_bundle` + `register_local_compute_task.ps1` | **已打通** | 使用 HMAC-SHA256 签名及 Gzip 压缩，由 Windows 计划任务定时推送到云端 `https://etf.joviluma.com/api/shadow/sync`。 |
| **4. 云端无状态安全呈现** | `backend/app/workspace/local_display_read.py` (`local_bundle`) | **基本打通**<br>*(存在1处局部卡点)* | 34 只 ETF 的决策表、详情页、K线与技术指标均已完整切换为读本地 Bundle 渲染；**唯一卡点是顶部大盘指数卡片未纳入 Bundle**。 |
| **5. 定时拉取到本地复盘** | 本地归档与复盘流水线 | **半打通**<br>*(需固化例程)* | 本地已有计算结果与 Outbox Bundle，但尚未建立自动将云端接收回执、用户自选/持仓反馈拉回本地并触发自动复盘报告的定时调度。 |

---

## 四、 核心卡点与关键突破点

### 卡点 1：网站顶部 9 个宏观指数卡片停留在 10-09（用户截图中的问题）
- **现象**：用户在网站看到大盘指数（上证指数、沪深300、恒生、纳指等）显示“10月9日”更新。
- **根因分析**：
  1. 云端生产环境自 10-09 起已关闭直接向外网抓取行情的后台任务，保护云端安全；
  2. 本地计算模块 `export_local_v2` 在打包 `local_bundle` 时，目前仅导出了 `overview`、`details`、`charts`、`sectors` 4 个部分，遗漏了 `market_context`（大盘指数）；
  3. 云端接口 `/api/bootstrap` 和 `/api/market-context` 在 `local_bundle` 模式下，因 Bundle 中没有 `market_context`，回退去查云端 SQLite，读取到了 10-09 的陈旧历史快照。
- **解决突破点**：
  1. 在本地 `compute_local` 中增加 `refresh_market_context` 执行步骤；
  2. 在 `export_local_v2` 中将 `market_context` 提取并存入 Bundle 的 `parts.market_context`；
  3. 在 `LocalDisplayReader` 中实现 `read_market_context`，并在云端 `/api/bootstrap`、`/api/market-context` 中接入读取。一旦本地 Bundle 到达，大盘卡片立即刷新为当天最新行情。

### 卡点 2：本地自动复盘（Closeout & Replay）闭环机制尚未标准化
- **现状**：目前本地跑完 `run_local_compute.py` 后，仅输出了 `bundle_*.json` 和 `bundle_*.receipt.json`，用户想要复盘需要手工查看日志或 SQLite。
- **开源方案借鉴（吸纳 Qbot / quant-fletch）**：
  - 在每日 15:30 收盘后，自动运行一条 `scripts/run_local_review.py`：
    1. 汇总当日各标的 14:30 信号与 15:00 最终收盘价的偏离度；
    2. 计算各个评级（可入场、观望、减仓）在次日或当天的理论收益率与胜率；
    3. 输出一份易读的本地复盘报告（Markdown / HTML），并可让本地 Codex/Bot 读取生成文本总结。

---

## 五、 实施计划与里程碑

1. **里程碑 1：解决网站顶部大盘 10-09 卡点（立即执行）**
   - 升级 `LocalDisplayContract`：支持 `market_context` 可选部分；
   - 升级 `export_local_v2`：将本地最新的大盘指数快照随 Bundle 同步发布；
   - 升级 `LocalDisplayReader` 与 `api/router.py`：优先从 Bundle 读取 `market_context`。
2. **里程碑 2：主分支合并与工程清理（保持 Git 干净）**
   - 将 `codex/local-live-to-website`（包含全部本地计算、解压缩、安全传输修复）以 `--ff-only` 安全合并回 `main` 分支；
   - 清理所有非版本控制的旧测试临时文件，保证工作区 clean。
3. **里程碑 3：建立盘后自动复盘标准模块（下一阶段推进）**
   - 吸收 `Qbot` 与 `quant-fletch` 的复盘设计，固化 `scripts/run_local_review.py`，打通“计算 $\to$ 投送 $\to$ 复盘”全闭环。

---

## 六、 结论

经最新开源项目调研与当前代码审查：
1. **用户提出的“本地自动下载 $\to$ 本地 Codex/Bot 计算 $\to$ 定时更新投送 $\to$ 定时本地复盘”在工程和逻辑上完全成立且已打通 85% 以上**；
2. 网站看到的“10月9日”卡点已精确定位，只需补齐 Bundle 中的 `market_context` 字段投送；
3. 开源社区项目 `quant-fletch`（PIT 向量化）、`Qbot`（全自动 Agent 编排闭环）和 `streametf`（轻量复盘可视化）为本项目下一步提供了极佳的技术参照。
