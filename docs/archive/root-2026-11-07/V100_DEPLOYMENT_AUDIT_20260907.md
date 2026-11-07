# v1.0.0 提交与部署核对

审阅基线：`9a0ca1812eda24acc390f1b3097662bfd615dfef`。本记录区分远端事实、本机自述和未验证事项。

## 可以独立核实

- `codex/v1.0.0` 确实指向该提交；annotated tag `v1.0.0` 的 tag object `178b6e72e5a7fb563e6f25f1de761b51d1a911b8` 也解析到同一提交。
- 核对时 `main` 仍为 `3c7bdc7ff36b3dea482651e087127a33c4974903`，尚未包含 v1.0.0。不能让后续 Agent 直接拉 main 就以为已取得新版。
- `GET /repos/Jovifei/ETF-Fund-Analysis/releases/tags/v1.0.0` 返回 404；标签存在不等于已创建独立 GitHub Release。未修改/重打该标签。
- Actions `ci` 34041693383、`workspace-ci` 34041693403 在该提交上成功。前者包括后端、迁移、Compose、镜像构建与容器 smoke，后者包括 Vue、类型检查、构建与标准 Chromium 浏览器测试。
- 下载 Actions artifact `9991888936`，SHA256 `b0a263c7e252a7f940e672ddbb84edbe5f5188c743e83421484b2ea39a207d57`。其 source.tar 的提交注记与 9a0ca181 一致。
- 对照原交付包，v1.0.0 增加了版本目录、SciPy 依赖、Windows 条件测试修复及版本信息；不是只有空标签。构建产物不入 Git，由 Vite/Docker 构建，这是正常流程。

核对入口：
- https://github.com/Jovifei/ETF-Fund-Analysis/tree/codex/v1.0.0
- https://github.com/Jovifei/ETF-Fund-Analysis/actions/runs/34041693383
- https://github.com/Jovifei/ETF-Fund-Analysis/actions/runs/34041693403

## 仅由本机发布记录报告，不能升级为远程实测

[原版本记录](versions/V1.0.0.md) 写明：AKShare 目录 5 条、两只 ETF 各 263 根日线、155 条新闻可读；现价 20 秒超时；Tushare/RSS 未配置；FTShare 拒绝且未入链；Windows 测试退出 0，临时 SQLite 退出时可能 WinError32。
这些是本机当次记录，不证明行情服务连续可用。此次没有远程进入 Jovi 的 Windows，也没有读取其 `127.0.0.1:8081`，没有操作 ECS/SSH、数据库、凭据或浏览器账户。

**结论：源码与演示交付基本按计划；“真实数据持久部署已完成”证据不足。** 临时 SQLite + Mock + 回环 demo 正是演示模式，不是 Tushare/AKShare 数据服务，不会因 APP_VERSION 改为 1.0.0 自动转成真实数据。

## 发现的实际代码问题

1. Tushare `rt_etf_k` 未传沪市专用 topic，未显式请求默认不输出的 `trade_time`。不能用实时 endpoint 名称代替时间资格。
2. 日线/实时源的成交量与成交额单位不同；旧数据无法在原地猜测一次乘系数修复。
3. AKShare 抓取时间被当作行情时间，代理卡片还曾标记 fresh；未有源时间必须保守处理。
4. 刷新跟踪池也会串行抓全目录和慢新闻/板块，影响页面拿到核心快照。
5. `sync_catalog` 调用审计缺少必需的 `run_id`，非空真实目录路径会触发错误；已新增测试覆盖。
6. 直接 AKShare/Tushare 模式曾绕过 RSS 组合；配置状态缺少可读的权限/依赖/数据覆盖区分。
7. STATUS/HANDOFF 仍保留“未推送”等交付时文字；v1.0.1 归档原文并建立当前入口。

v1.0.1 修复与配置路径见 [数据接入](DATA_ACCESS_V101.md)。Docker 云端 CI 成功不等于用户机器已经部署成功；复跑 `scripts/audit_workspace_deployment.py` 只能出具其实际观察范围内的 HTTP 检查报告。
