# 本地 Codex：WorkBuddy 风格决策看板验收 Prompt

你现在接收仓库：

`https://github.com/Jovifei/ETF-Fund-Analysis`

工作分支：

`feat/workbuddy-decision-board-replica-v2`

本轮只验收和修复新决策看板，不自动合并 `main`。

## 目标

新首页 `/` 是面向每天 ETF 研究决策的彩色评分台：

- 每只 ETF 显示 0–100 **读取层研究得分**；
- 红色代表强共振、橙色偏强、金色尚可、蓝色谨慎、绿色风险；
- 同时保留后端五档分级：可加仓 / 可入场 / 可试探 / 观望 / 减仓；
- 显示趋势、动量、量能、结构、预测、数据资格六维分；
- 明确解释 MA / MACD / KDJ / RSI / TD9 / 量能；
- KDJ J 值必须明确显示 `J>=90` 偏热、不追高的语义；
- 1 / 3 / 5 / 10 日预测可切换；
- 每卡显示 Provider、源时间、实时/验证状态；
- 点击 ETF 打开详情，显示历史 K 线 + 紫色未来研究情景 K 线 + 支撑/压力；
- `/legacy` 继续提供原完整多页签系统。

注意：用户提供的 WorkBuddy 动态分享链接在远端自动抓取环境中无法读取，因此当前实现不宣称像素级复制外站；本轮依据用户描述、此前任务截图和现有 API 契约复刻其信息架构。

## 第一步：安全拉取

```bash
git status --short
git fetch origin --prune --tags
git checkout feat/workbuddy-decision-board-replica-v2
git pull --ff-only origin feat/workbuddy-decision-board-replica-v2
git log -12 --oneline
git diff --stat origin/main...HEAD
```

不得 reset/clean/stash 用户未提交内容。

## 第二步：阅读

- `AGENTS.md`
- `docs/DECISION_BOARD_WORKBUDDY_REPLICA.md`
- `backend/app/static/decision_board_workbuddy.html`
- `backend/app/static/decision_board_workbuddy.css`
- `backend/app/static/decision_board_workbuddy.js`
- `backend/app/static/decision_board_workbuddy.test.js`
- `backend/tests/test_workbuddy_decision_board.py`

## 第三步：代码门禁

```bash
pytest -q
python -m compileall -q backend/app
node --check backend/app/static/app.js
node --check backend/app/static/decision_board_workbuddy.js
node --test backend/app/static/decision_board_workbuddy.test.js
python codex/skills/fund-research/scripts/check_no_secrets.py .
```

若完整 CI 最后只因 `scripts/qualify_postgres.sh` 的既有 ShellCheck 问题失败，必须把它单独记录为继承自 `main` 的发布门禁问题，不允许通过 `|| true`、删除 ShellCheck 或大范围 suppress 来伪造绿色。

## 第四步：Mock / 本地页面

使用现有安全测试配置启动应用；不得读取或输出 `.env`。

重点访问：

- `/` 新评分台
- `/legacy` 原完整系统
- `/workbench/1430` 应 307 到 `/`

浏览器至少验证：

- 1440px
- 1024px
- 390px

检查：

1. 首页明显为深色彩色，不是黑白表格；
2. 每只 ETF 有清晰的大号综合分；
3. 得分颜色与分值区间一致；
4. 六维得分条均可见；
5. `J=89` 与 `J=90` 的解释边界不同；
6. KDJ 死叉明显降权；
7. RSI、MACD、MA、量比、TD9 解读不混淆；
8. 1/3/5/10 日预测均可切换；
9. `not_calibrated` 不被写成“准确率”；
10. Mock/stale/unverified 会在数据资格上降分并出现警告；
11. 五档分组与 0–100 显示分是两套概念，不互相覆盖；
12. 点击 ETF 能看到详情与 K 线；
13. 未来紫色 K 线明确标记“非实际结果”；
14. 支撑和压力线可见；
15. Provider、源时间、验证状态可见；
16. `/legacy` 的持仓、新闻、系统设置仍然存在。

## 第五步：评分语义审查

当前 UI 评分权重：

- 趋势 22%
- 动量 22%
- 量能 14%
- 结构 14%
- 当前预测期限 20%
- 数据资格 8%

它只能是“显示/解释层研究分”。

禁止：

- 写入 `SignalV05Service`；
- 修改生产信号阈值；
- 自动调整持仓；
- 自动下单；
- 把 80 分解释为 80% 上涨概率；
- 把未校准预测置信度叫准确率。

KDJ J 规则必须保持：

- J > 100：超买/钝化，回撤风险高；
- 90 <= J <= 100：偏热，不追高；
- 70 <= J < 90：偏强，仍有余量；
- 30 <= J < 70：健康区；
- 10 <= J < 30：低位，等待拐头；
- J < 10：极低/超卖，但不是自动买点；
- KDJ 死叉优先降分。

## 第六步：输出报告

创建：

`deployment_reports/YYYY-MM-DD-workbuddy-board-local-review.md`

至少包含：

- Git SHA；
- pytest；
- Node test；
- 1440/1024/390 截图；
- 六维评分审查；
- J=90 边界审查；
- 预测周期切换；
- Provider/时效显示；
- 新首页与 `/legacy` 回归；
- 与用户参考目标仍有的视觉差距；
- 已知继承自 main 的 CI / Docker 发布阻塞项；
- 是否建议继续打磨 / 是否建议合并。

不要自动 push，不要自动 merge。完成后先向用户汇报。
