# main整合、清理与当前卡点（2026-10-14启动，10-15完成）

Jovi授权把有效功能统一到main、核卡点及清理可重建残留；后续又明确确认Owner完成的大盘上下文改动应一起纳入。本轮不部署、不抓真实行情、不修改数据库、持仓或私有配置。

## 交付身份

- [PR46](https://github.com/Jovifei/ETF-Fund-Analysis/pull/46)已合并；main代码合并提交f2d517d8b5cd0895d13eb3860c0d90c05b9a8be8，树与已验证实现888122c07b5768bab3192f91c47b775bfbdb58c6完全一致。
- 原目录已使用git pull --ff-only对齐GitHub main，工作树干净；本收据及状态更新的后继提交只改文档/任务记录，不替代上述源码验证身份。
- Owner原始完成稿保存为a9661ff437c4500e921bff37121b8bf3bd798101并保留在合并历史；原未提交接收候选工作树、私有配置、数据库和失败证据均未覆盖。没有reset/clean/stash或force push。

## 分支处理

| 来源 | 处理/原因 |
|---|---|
| codex/local-live-to-website a2adee5及Owner a9661ff | 合入当前功能与大盘market_context采集/投影/读取，保留原完成稿 |
| codex/local-execution-20261011 91f7447 | 原未推图表/类型/收据校验有独立价值，已整合；客户端采用后续兼容实现，不回退gzip或V2回执 |
| receiver-safety-20261013未提交候选 | 接收安全v1.1/v2.1整合：有界解压、发布前预算、锁所有权、存储读取身份/哈希/类型重验、版本化回执；保留a2新增decision-board/持仓接线 |
| post-release-indicator-audit d013e48 | 独立observed-close估值/fill ledger对账修复合入；backtest_version升至0.5.8-observed-mark-ledger，strategy hash变化需后续重新绑定发布/快照 |
| local-live-display-plan 3c26f47 | 最终方案/接手文档已接收，当前todo优先，历史记录保留 |
| rollout/chart-dpr 8cd25b3 | 已提交部分只有发布收据，已接收；未提交浏览器候选/截图保留，未冒称DPR专项通过 |
| local-chart-algorithm-acceptance 30b7c68 | 独有44提交均为历史审计/交接，无独立业务源；保留历史分支，不回带旧元数据 |
| review-integration 6908544 | 旧源码片段传输/审计记录，仅历史参考，不复制进当前运行路径 |
| shadow-auth-followup 97d542b | 功能已通过d6dd03a及本次安全接收包含，保留原引用，不重复带入旧实现 |
| s2-availability c8af982 | 按Jovi此前明确决定保留历史，新版已替代旧语义，不合入旧候选 |
| 其余已包含旧分支 | 属于main历史而非漏合功能；相关工作树/Owner未提交Chan研究稿保留，不擅自删除或覆盖 |

## 验证（按各自身份，非生产验收）

| 检查 | 实际结果 |
|---|---|
| 整合基础cb0aea4完整后端 |1983总例：1960 PASS、23 SKIP、0 FAIL/ERROR；741.875s |
| 后续Owner market_context追加 |152 PASS、0 SKIP/FAIL；30.820s；已包含受影响API、投影/读、市场上下文与安全回归 |
| 真实锁定前端依赖 |Vitest4.1.11，200 PASS/25文件，typecheck/build通过 |
| Node静态回归 |27 PASS/0FAIL，app.js语法检查通过 |
| compileall/committed-secret/diff检查 |通过；未输出秘密 |
| 实现888精确GitHub push CI |ci38592188985、workspace38592188499、audit38592188628均SUCCESS；PR重复主CI在最后收据观察时仍运行，另三项PR工作流已SUCCESS |
| 原目录依赖/构建 |发现旧node_modules实际Vitest3.2.7与lock不符；独立fresh install验证后，根目录npm ci按lock重装，typecheck/build通过，未改lock或升级依赖 |

首次backtest新增测试有helper名引用错误，修正为现有_latest_observed_close，断言保持。旧持仓测试只给无成交当日、没有历史有效mark，新fail-closed门槛正确拒绝；给“保持持仓不交易”夹具增加此前observed close，另保留“无任何可靠mark必须拒绝”的负例。首次全量1失败、收集/聚焦失败XML与修正后的9项通过证据均保留在隔离验证目录。没有删失败用例或降低门禁。

## 清理与保护

- 自动审批拒绝批量递归删除缓存，未返回更具体理由；没有绕过。
- 改为可回滚归档：19个未tracked、非符号链接、确认为可重建的root .pytest_cache及__pycache__，总9672348bytes（约9.22MiB）。已移到.local/cache-archive-20261014；这是原目录整理，不是磁盘释放。
- 未删除有效测试源码。截图/trace、原失败收据、数据库、配置、持仓、回滚镜像/备份、.venv与其他工作树均保留。
- 本轮自己的补丁/XML已移入整合工作树.local/validation-20261014，不让临时文件成为根目录未提交项。
- 原开源评估稿保留在a966历史，当前文档修正了未经核验的完成/34只范围及许可证声明；Qbot主仓许可信息与README说明需具体文件核对，streametf未识别许可证，不凭名称自动复制代码。

## 现在真正卡在哪里

1. **过期激活与当前版本绑定**：安全接收版本明确未改变历史STALE读取政策；过期包是否允许激活、当前code/config对应与各消费者降级语义仍需统一。
2. **正常网站同代语义**：前端跨请求generation pin、horizon/snapshot_id选择、无包/空part回退云端、私有持仓价格代数尚未全部闭环。market_context接线已合，不等于指数实时性/许可已核验。
3. **云端完全停止计算写入**：scheduler关闭只是一个入口；通用任务/手工/admin/worker需要display-only准入及真实两交易日rows/bytes对照。
4. **引导/partial与复盘**：bootstrap dry-run可能先sync、失败status和partial资格、覆盖不仅数bars、固定本机复盘与接收反馈边界需要落实。复盘收益按真实horizon实现时点验证，不能提前填胜率。
5. **部署与资源/科学资格**：本轮只读实际生产仍e30f143/image51507753，未部署整合源码。最新根目录main会改变下一次本机任务的code/strategy身份，真实上传/收据/兼容性应单独核验；许可/PIT/OOS/7–14交易日soak/手机DPR仍独立，UNKNOWN/actionable=false/not_calibrated不晋升。

## 复审/上报限制

实际独立本地源码复审确认本轮新增接线没有阻止源码合main的新回归。网页端指定本地连接失败，未签发独立源码通过；它的条件性意见不能冒作实读复审PASS，现有Pro还在响应用户的新架构问题。本轮未凭此推荐部署。

Hub revision读取WinError10061，未取得新revision/未发送成功；待上报摘要另存本地，不伪造event或重试旧失败事件。

下一阶段先完成上述链路门槛，再用精确源码测试/网页端GitHub复审/新备份及可回滚发布验收。当前是MAIN_CONSOLIDATED_AND_CLEAN，而非生产或全项目完成。
