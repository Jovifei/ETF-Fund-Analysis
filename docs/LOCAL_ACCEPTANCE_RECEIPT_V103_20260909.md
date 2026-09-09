# v1.0.3 本地接收与验收收据（2026-09-09）

## 结论与版本

本地日线/历史图表已接入原持久库；整体为**部分验收通过**，未宣称所有真实数据能力、本人会话或 AI/OCR 合格。

- 用户指定固定应用提交：`9439563dafc35d7410f9dde39253478a321c96ef`，基线 `204a31cbc0214a6e80389224c238bc897b2279af`；祖先关系已验证。
- 固定接收目录：`E:/Claude_allow/Download/ETF-Fund-Analysis-v103-receive-20260909`，应用源码保持指定提交；只增加工作记录/本收据。
- 必要修复单独提交：`a628004236f19cd31bf1d69a6e8e101567e60fff`（完整行情缓存保护、指数入口与失败摘要），`49ab0ce9d29405e0d4735e41e9ccc642d7904784`（板块重复/冲突记录隔离）。
- **当前本机运行应用 SHA：`49ab0ce9d29405e0d4735e41e9ccc642d7904784`**；审核分支 `codex/v103-local-review-20260909`。两个修复提交仅在本机，未推送、未合并 main、未改标签、未部署服务器。
- 运行目录：`E:/Claude_allow/Download/ETF-Fund-Analysis-v103-review-20260909`；URL：<http://127.0.0.1:8082/>。
- Python 3.12.10，Node 24.18.0，npm 11.16.0；独立安装 `.[dev,market]` 与锁文件 `npm ci`。最终后端使用同一新 Python 环境和明确指向运行目录的 PYTHONPATH。
- 应用版本 1.0.3；策略 `signal-v0.7.1-research`，指标 `indicator-v0.5.1`，预测 `similarity-corridor-v0.7.1-horizon-aligned`，数据口径 `cn-fund-shares-cny-v1.0.1`；均未修改公式、单位、权重、期限或资格。

## 工作区与数据库保护

原工程 `E:/project/ETF-Fund-Analysis` 保持 `11fb295352246769b4f2ae9efaf07d5333bc9c44`；19 个已暂存文件的状态及 staged/unstaged diff 指纹前后一致。未 reset/clean/stash。

使用原外部持久库 `E:/Claude_allow/Download/ETF-Fund-Analysis_v101_live_20260907/data/workspace.sqlite3`，未重新 init。接收前用 SQLite backup API 做一致性备份，完整性为 ok；在副本上 Alembic upgrade/check 均通过，head 为 `d40609090002`，原库无需 schema 升级。

固定 SHA 的真实试验暴露出 Sina 价格回退会覆盖同日完整缓存。保留整个试验库后，确认服务无用户 HTTP 写入且私人表计数未变，停止本任务所属 API/worker，恢复接收前一致性备份，再在修复版重跑。两份数据库都保留在私有证据目录。原账户、会话、持仓、自选计数保持不变；未读取/重置密码，未新增真实账户，未删除报告。

原私有配置未覆盖；使用仓库外私有副本，显式 `WORKSPACE_DISCOVERY_ENABLED=false`，Bridge/定时复盘/模型调用关闭。AUTH_ENABLED=true、AUTO_CREATE_SCHEMA=false、ALLOW_MOCK_FALLBACK=false；仅回环 HTTP 使用非 Secure Cookie。API 与 worker 由同一个已检查 SHA 的 launcher、相同代码目录及原库启动。

## 本机新验证

| 项目 | 结果 |
|---|---|
| 固定 SHA 全量 pytest | 838 passed，5 条件跳过，exit 0 |
| 固定 SHA v103 专项 | 15 passed，exit 0 |
| 最终修复全量 pytest | 842 passed，5 条件跳过，exit 0 |
| Vue | 24 单元测试、typecheck、生产 build 通过 |
| workspace-ci 普通/认证 Playwright | 修复后 12 + 1 通过；均为隔离 Mock 夹具 |
| 真实行情缓存回放浏览器 | 11/11 通过，合成账户，0 page errors，0 外部请求 |
| 旧 JS | CI 指定 7 个脚本语法通过；19 个 Node 测试通过 |
| compileall、密钥扫描、diff 检查 | 通过；未自动修正依赖版本 |
| npm audit --audit-level=high | exit 0；仍有 1 low、2 moderate，未执行 audit fix |
| 临时空 SQLite + 原库副本 Alembic | 各自 upgrade/check 通过，head 单一，integrity ok |

五个后端跳过：四项 Windows 符号链接权限条件测试；一项未配置专用 TEST_POSTGRES_URL。Docker 引擎不可用，未拿用户数据库代替 PostgreSQL 测试。后端 pytest 串行运行；普通/认证浏览器使用独立临时目录。

## L1：最终原库中的真实能力

| 能力 | 当前入库与来源 | 时效/限制 |
|---|---|---|
| 510300.SH | 283 根，`akshare:sina:v101` | 2025-07-14 至 2026-09-08；283 根缺量，价格指标可展示，量价/操作资格不提升 |
| 512480.SH | 282 根完整 `akshare:em:v101` + 1 根 `akshare:sina:v101` | 截至 2026-09-08；旧完整行全部保留，只新日期缺量 |
| 上证 cn-shanghai-composite | 799 根真实 `akshare:index:v103` OHLC | 至 2026-09-09；当天为未收盘日线，不当作实时或确定收盘 |
| 沪深300 cn-csi300 | 799 根真实 `akshare:index:v103` OHLC | 同上；开高低收存在真实差异，未复制收盘点值 |
| 中证全指 cn-csi-all | 0 根 | EM 路径 ProviderError；Sina 返回 1180 根但最新仅 2016-06-13，目标时间窗内为 0；最终 CapabilityUnavailable |
| 当前目录 | 1,986：EM ETF 1,604 + Sina LOF 382 | 2026-09-09 重跑更新 1,986；没有将目录全量加入研究池 |
| 行业/概念/全市场 | 最后一次任务分别处理 90 / 175 / 1，status=succeeded | 源日期 2026-09-09；条数不代表每个板块字段完整或交易所全量 |
| 实时报价 | 当前同步失败，ProviderError | 未取得新的可靠实时时间戳；历史收盘展示独立可用 |

第一次固定 SHA 试验的 Sina 目录返回 2,039；该试验已整体保留后回滚。当前重跑优先源返回 1,986，以上表格描述的是**最终库**，不能将不同来源的返回数量当作全市场覆盖证明。

缓存重算实际执行，状态 partial；最终指标快照表有 3 行。缺量、陈旧数据或其他输入门禁仍会使共享计算跳过标的。两只目标 ETF 的只读图表均有 MA/MACD/KDJ/RSI，quote_status=historical_close，actionable=false。并未生成新校准概率。

成功和失败任务、ProviderAudit、源日期与数量已留存在本机；任务失败另有 TaskRun 与净化日志。部分失败只保留类型化原因，未保留底层 SDK 原始响应，不能反推更精确的网络错误或 SDK 级耗时。

## 真实发现与修复边界

1. 完整历史被低质量回退覆盖：已用 RED 复现，修复后整行保留，不混拼来源字段；新日期仍可接收 price-only，完整源恢复后仍可替换。原库重跑验证 512480.SH 的 282 个完整缓存行未再降级。
2. 不支持的海外指数显示 A 股下载按钮：已隐藏，并明确能力未实现；三只受支持指数入口保留。
3. 指数 task summary 丢失逐指数原因：现保留有界、类型化 context_id/reason，原始错误字段过滤；实际断网试验中看到三只指数各自的 CapabilityUnavailable。
4. 板块重复键边界：autoflush=False 下重复新记录可触发唯一约束，已确定性 RED/GREEN。相同值去重，冲突值不选第一/最后条，保留旧缓存并标 partial，其他有效记录继续。最初真实失败批次未留存，故**不能断言其唯一根因已被证明**。最终真实重跑 exit 0，90/175/1，duplicate_records=0、conflict_keys=0。

## 缓存、归档与磁盘

API/worker 已重启。在只对本任务进程设置不可达外部 HTTP 代理后，真实 worker 再次尝试指数下载，三只全部失败；两只已有指数与两只 ETF 的条数、日期和哈希保持一致。额外只读检查拒绝所有 socket.connect，仍能读取价格指标。之后恢复正常网络并启动最终代码；最终缓存哈希再次与断网前一致。本人登录后的真实 HTTP GET 仍待用户会话，未以 health 200 替代它。

`market-archive-reviewed` 导出 566 条 ETF 日线 + 2 个指数缓存；gzip 47,849 bytes，SHA256 校验通过；重复目录拒绝且原文件哈希不变。仅公共行情，无账户、持仓、凭据。仅为归档，不是已实现的生产重导入或双向同步。

最终数据库 3940352 bytes（约 3.76 MiB），接收前 2,031,616 bytes。没有磁盘不足的证据。

## L2：浏览器证据

CI 夹具验收通过；另从已封存的公开行情包回放到新的临时数据库，使用合成测试管理员，完成登录/退出、真实缓存 K 线与指标、沪深300 OHLC、原 WorkBuddy 筛选/5 日期限/返回保留、详情/目录/原表收藏一致、目录收藏不跳转和取消任务不跳转。最终回放服务没有连接原库；早期只读可用性核查仅访问共享行情表，未读取/复制私人表。

截图页首明确标注“真实行情缓存回放 · 合成测试账户 · 非本人会话验收”：

- [ETF 历史与指标](E:/Claude_allow/Download/v103-acceptance-20260909/real-cache-browser/02-etf-510300-chart.png)
- [原模板与筛选期限](E:/Claude_allow/Download/v103-acceptance-20260909/real-cache-browser/03-original-filter-horizon.png)
- [指数蜡烛图](E:/Claude_allow/Download/v103-acceptance-20260909/real-cache-browser/04-index-csi300-chart.png)
- [收藏同步](E:/Claude_allow/Download/v103-acceptance-20260909/real-cache-browser/05-favorite-sync.png)

临时服务 18086 已停止；未使用用户真实账号作测试。本人现有管理员会话的页面验收仍待登录。

## L3：OCR

已独立安装 Python 3.12.10、PaddlePaddle 3.3.1、PaddleOCR 3.7.0、Pillow 12.3.0，下载官方模型并尝试合成图。

结果 BLOCKED_OCR_L3：v5 新模型文件布局被现有 manifest 白名单拒绝；旧 v3 manifest 可过，但 OCR 3.7 引擎要求 inference.yml，最终 engine_unavailable；直接 v5 也遇到 Paddle oneDNN NotImplementedError。属于模型/代码契约兼容问题，不是只补配置即可启用。实际识别未成功。约 0.266 秒硬超时试验、子进程清理、source.img 清理通过；真实图片未提供，未上传云端。本站保持 OCR disabled、手工录入可用。

## L4：Codex / Vibe

Vibe 固定 `09e8404a33ba0d05e036e01207be4701c61d692c` 安装 exit 0；verify exit 1、not_qualified。TypeScript、desktop tests/build 通过；orchestrator 和 calculation 测试因 Windows symlink/路径/环境问题失败。未尝试把公司深研产物冒充 ETF 研判。

Bridge doctor exit 0、Windows DPAPI、paired=false。独立安装官方 `@openai/codex@0.149.0`，wrapper 与 native binary 均核对版本，专用 CODEX_HOME 下 MCP 列表为 []。未复制全局 auth.json，未执行登录、配对、模型调用或付费 API。

[本人官方登录步骤](E:/Claude_allow/Download/v103-acceptance-20260909/vibe/BRIDGE_CODEX_LOGIN_V103.md) 已准备。真实研究仍需本人官方登录、明确单次模型/预算及配对，站点 Bridge 目前关闭。Vibe Windows 资格失败单独保留，不能用安装成功替代资格。

## L5：复盘、因子、归档

- 人工复盘的保存/刷新持久性、修订冲突和跨用户隔离通过隔离测试；本人真实笔记未代写。
- 实际队列提交 `rsi14/macd_norm/return_20d` 三个注册因子，失败为 HistoryContractError（池内历史缺量），没有输出诊断矩阵或 1/3/5/10 新概率，未调整/启用策略。
- 行情归档真实执行及哈希/重复目录检查通过，见上。
- 网站 API Key Secret Store、可信行情重导入/自动双向同步、月度预测、自动策略训练仍未实现；q code 产品未确认。

## 下一步

刷新 <http://127.0.0.1:8082/>，由本人使用原管理员账号登录，继续验证真人会话中的原模板、收藏与详情入口。不要把密码发到聊天。中证全指/实时源、完整量能、OCR 兼容、Vibe Windows 资格及单次模型试点分别保持未通过/待本人动作，不阻断已验证的历史价格展示。

本次应用修复只提交本地审核分支。详细日志、原始数据库与模型产物在仓库外私有目录；本文件只保留净化摘要。

## 未通过项的复现入口

以下只做本机诊断/合成图/离线源码测试，不调用模型。使用独立解释器；不要指向生产配置或数据库。

```powershell
# 中证全指当前受支持路径：有界、只读取数；不写库
& 'E:\Claude_allow\Download\ETF-Fund-Analysis-v103-receive-20260909\.venv\Scripts\python.exe' 'E:\Claude_allow\Download\v103-acceptance-20260909\probe-csi.py'

# OCR 合成图 + 现有官方 v3 模型的兼容/超时复现
& 'E:\AI_Tools\Other\ETF-OCR-v103\venv\Scripts\python.exe' 'E:\Claude_allow\Download\v103-acceptance-20260909\ocr\run_synthetic_ocr_trial.py'

# Vibe 固定安装的源码资格复测；不是模型任务
& 'E:\Claude_allow\Download\ETF-Fund-Analysis-v103-receive-20260909\.venv\Scripts\python.exe' 'E:\Claude_allow\Download\ETF-Fund-Analysis-v103-review-20260909\scripts\vibe_trial.py' verify --root 'E:\AI_Tools\Other\Vibe-v103-20260909' --max-minutes 30
```

因子门禁复现：本人登录后，在因子页选择 rsi14、macd_norm、return_20d 提交；池内缺量未补齐前，真实诊断不能通过。不要删除该门禁或以 Mock 代替。
