# 本次 ZIP 验收记录

日期：2026-09-06；对象：恢复 7adfbc0 后追加修复的工作站 rc.2。不是引用以前 main 的705项测试。

| 检查 | 实际结果 | 说明 |
|---|---|---|
| 全量 pytest | **782 passed / 1 skipped / 0 failed / 0 errors**，783 cases，224.583秒 | `evidence/pytest-full.xml`；未设置 TEST_POSTGRES_URL 的 PostgreSQL 并发初始化测试跳过 |
| 最终相关后端回归 | **33 passed** | external-research、ingestion、workspace contract；覆盖全量测试后追加的幂等异常保护 |
| Vue Vitest | **19 passed / 6 files** | API竞态、session序号、图表数值、导航、App等 |
| Vue TypeScript | 通过 | `npm run typecheck --prefix frontend` |
| Vue production build | 通过，rc.2 静态资源随包提供 | `npm run build --prefix frontend` |
| 旧浏览器 JS 单测 | **19 passed** | 原 decision_board_workbuddy / legacy_route 保留 |
| Python compileall、旧 JS 语法 | 通过 | 不替代测试 |
| Alembic clean SQLite | upgrade、check、单head通过 | 新 head `d40609090002`；不是 PostgreSQL 迁移实测 |
| 预构建页面 + ASGI smoke | 通过 | 5个入口、CSS/JS、CSP、安全404、搜索/图表；不需要网络 |
| 离线真实浏览器组件 + ASGI | **5组流程通过，0 page errors，28次真实应用API调用** | 实际 Vue、真实KLine canvas、临时SQLite/Mock；7张截图 |
| 标准 URL/HTTP Playwright | **未通过当前环境执行条件** | 受管 Chromium 的 URLBlocklist 阻止导航，ERR_BLOCKED_BY_ADMINISTRATOR；未更改或绕过策略 |
| Docker/Compose、PostgreSQL联调 | 未在当前环境执行 | 当前没有 Docker daemon/测试PostgreSQL；CI门禁和测试脚本保留 |
| 实时行情/真实OCR/真实模型 | 未在当前环境验收 | 不以合成数据/假模型冒充 |

## 浏览器证据准确解释

`frontend/validation` 构建真实组件的独立测试入口，memory router 运行在空白页；Python Playwright binding 将组件 fetch 交给真实 FastAPI TestClient。
它没有导航到被管理策略封锁的地址，没有解除浏览器限制，没有请求生产服务。它验证界面与真实API的交互，但没有验证生产HTTP传输、Cookie浏览器行为、TLS、生产CSP执行。
真实 Cookie/CSRF 与用户隔离另由 ASGI 集成测试覆盖；发布前仍需在可访问的受控环境运行 `npm run test:e2e --prefix frontend`。
截图全部使用模拟市场及测试持仓；只作功能和视觉验收。

## 修复前后证据

恢复源码的第一次全量运行为747通过、5失败、1跳过。5个失败来自已有模拟 AKShare 测试却强制导入未安装的可选包。
修复为显式 `ak_client` 依赖注入，沿用原测试断言；没有伪装安装AKShare或删掉对应测试。
新增行情批写入测试先复现每100根103次SELECT，再约束修改后≤5次；校验非法价格和批次冲突。
新增前端延迟响应测试先复现退出/换用户后旧数据仍可返回，再添加epoch失效保护。
新增Vibe路径在未实现时因缺模块/404失败，补齐后包括用户隔离/CSRF在内通过。

第二轮全量曾因旧 signal_center 测试把“总机会数量”误等同“前10列表长度”失败。按照其原合同改为 min(total, front_size)，并新增多个front_size下总数保持一致的断言；没有改评分或筛选规则掩盖失败。
最新全量结果见首表。测试日志仍有 SQLite datetime 弃用与孤立组件路由 fixture 警告，非失败；不声称环境零警告。

## 环境、可复现性与依赖边界

当前实际运行 Python3.13.5、Node22.16.0；交付推荐Python3.12/Node≥22.18，Vibe最低Node22.18。
使用隔离venv并复用当前环境已有库、恢复的锁定Node依赖；不是联网从零安装验证。
前端 npm lock 固定，当前无网络未再次查询依赖漏洞库。不得把此前audit快照当作当前安全保证；CI保留npm audit门禁。
依赖版本与产物摘要见 `evidence/verification.json`。完整源码可在联网干净环境重新执行保留的全部CI。

## 复跑命令

```bash
python -m pytest -q
python -m compileall -q backend/app scripts bridge
node --check backend/app/static/app.js
node --test backend/app/static/decision_board_workbuddy.test.js backend/app/static/legacy_route.test.js
npm ci --prefix frontend
npm run typecheck --prefix frontend
npm run test --prefix frontend
npm run build --prefix frontend
npm run test:e2e --prefix frontend
python scripts/run_workspace_demo.py --smoke
```

PostgreSQL、Compose、安全扫描、生产镜像smoke需独立复跑；不能把代码资格等同策略盈利资格。
