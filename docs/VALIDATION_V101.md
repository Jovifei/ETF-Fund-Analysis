# v1.0.1 最终验证与证据边界

日期：2026-09-07（Asia/Shanghai）。精确基线：9a0ca1812eda24acc390f1b3097662bfd615dfef。
本报告对应本次完整包/增量补丁，不引用 v1.0.0 的云端绿灯来替代本版。

## 本次实际执行

| 检查 | 结果 / 范围 |
|---|---|
| 后端全量 pytest | **812 项收集，811 通过、1 跳过、0 失败、0 错误**；227.6 秒 |
| Vue Vitest | 19 项通过 |
| 旧浏览器 JavaScript 单测 | 19 项通过 |
| TypeScript / Vite production build | 通过；构建结果随完整包提供 |
| Python compileall / 7 个原 JS 语法检查 | 通过 |
| Alembic clean SQLite upgrade / check / heads | 通过；唯一 head d40609090002；本版没有 Schema 变更 |
| 密钥扫描 / git diff --check | 通过；未为了绿灯关闭扫描 |
| YAML 语法 | Compose / 两份相关 workflow 可解析；不是 Docker 运行证明 |
| 持久化真实 HTTP 进程检查 | **14 项通过**；Linux 隔离新数据库、官方管理员 CLI、回环 API+worker |
| 实际组件离线浏览器 | **8 组流程通过，0 页面错误，38 次真实 ASGI 请求**；Mock，仅功能验收 |

跳过项是需要 TEST_POSTGRES_URL 的 PostgreSQL 条件测试，未配置该服务。此处环境 Python 3.13.5；生产/本机复跑推荐 Python 3.12。没有本版远端 CI、Docker/PostgreSQL、ShellCheck 或 Windows 执行成功的声明。

## HTTP 与浏览器分别证明了什么

真实 HTTP 检查实际运行 `run_workspace_live.py init/bootstrap-admin/serve`，读取 HTTP 1.0.1/非 Mock 配置，核验未登录 401、HttpOnly 登录 Cookie、缺 CSRF 拒绝、退出后撤销、页面与静态文件、停止仍保留数据库。使用一次性随机测试密码，不保留/输出密码和 Cookie；没有抓真实行情、没有读取用户数据库。
这不是 Jovi 本机或 ECS 检查，也不是生产 TLS/Secure Cookie/PostgreSQL 联调。

普通 Chromium URL 导航在当前容器受到管理员策略阻断，未关闭或绕过该策略，标准 Playwright 网络导航没有在这里通过。保留标准 4 条旧 E2E 与新增 1 条 v1.0.1 用例，供正常环境 CI 复跑。
离线 harness 在 about:blank 加载实际 Vue/KLineCharts 代码，通过受控 binding 调用真实 ASGI 测试应用，不进行网络导航。覆盖总览、搜索/自选、ETF 图表、持仓确认/成本线、外部研究候选、因子/移动端、数据接入与任务排队；并实际加载原 HTML/CSS/JS 检查经典 ETF 面板。
所有截图与研究包示例是 Mock/测试持仓，不可作为行情、收益或真实模型结果。

## 外部数据可用性

本容器公共探测实际输出：AKShare 依赖不可用（called=false），Tushare 未配置（called=false），FTShare/RSS 未探测。不能把脚本 exit 0 / probe_complete=true 误读成外网接通。
使用注入客户端的测试验证了 Tushare 参数、字段、单位、时间解析、AK 回退、硬截止与子进程回收、审计、旧口径全覆盖替换、核心任务部分失败、分钟线、只读配置和源时间覆盖。但**没有本人 Token/真实权限验证或持续公网采集 SLA**。
上游官方文档依据和条件见 [DATA_ACCESS_V101.md](DATA_ACCESS_V101.md)。v1.0.0 本机当次 AKShare 成功记录仍只是那次记录。

## 过程中的失败不是被删除的验收项

先添加失败测试再修复。初次全量出现两个旧不安全语义断言：原始异常文本透传，以及无可靠源时间的 AK 代理被标 fresh。现改为更严格的脱敏/时间合同；相关测试继续存在。
后续全量发现新交接文档遗漏生产认证参数，补回原硬合同后通过。收尾发现价格回退历史可能卡在增量窗口外、工作器心跳 DB 锁可能遗留任务进程、接入覆盖误称抓取时间为源时间，均补了回归测试并运行上述最终全量。

## 证据文件

本包的 `evidence/v1.0.1/` 保存本版 pytest XML、Vue/构建/旧 JS 输出、Alembic结果、脱敏 HTTP 检查、浏览器检查和公共探测结果；根 `evidence/` 原有文件属于 v1.0.0/原交付历史。
完整包 `PACKAGE_MANIFEST_V101.json` 校验源码、构建产物与证据，`DELIVERY_MANIFEST.json` 仅归档历史。压缩包另有 SHA256 文件。提交、重新构建后字节改变是预期，不应改旧证据伪造未变更。

## 2026-09-07 接收复验

- 原 ZIP SHA256 为 `EA1F2CDB8629C3E9598D1626A59FDDD03A5248E51F0D02CF22BB033B14334F49`，562 个归档项无路径穿越/绝对路径/依赖目录；包校验 561/561 通过。
- 隔离 Windows clone 从 `9a0ca181` 建分支后，后端全量 812 项收集、0 失败；5 个跳过均为 Windows 符号链接权限或 PostgreSQL 条件门禁。Vue 19、原 JS 19、TypeScript、build、compileall、Alembic 单 head、secret scan 通过。
- 标准 Playwright 使用临时端口 18083（18082 被其他项目占用）实际 5/5 通过；Matrix `scope=col` 和测试 fixture 清理是本次最小修复。Docker 生产式镜像 build 与临时 PostgreSQL API smoke 通过；ShellCheck 9 个脚本、两套 Compose 静态 config 通过。
- 公共数据探测：AKShare 两只 ETF 日线各 241 根，来源为 `akshare:sina:v101`、成交量缺失；新闻 200 条；目录与公开 quote 本次 unavailable；Tushare credentials_missing、FTShare/RSS 未探测。全部 `actionable=false`。
- 隔离两标的真实任务只处理 `510300.SH`、`512480.SH`，写入 562 根价格日线；因 Sina 缺量，指标/预测/信号/快照按合同跳过并标记 `partial`，没有用零填充或 Mock 补齐。
- 远端生产仅完成只读盘点与一次现有 Compose 数据库备份；生产当前仍为 0.8.0/root Compose，迁移头 `c2d3e4f5a6b7`，未执行代码切换、数据重抓、Docker 重启或代理切换。
