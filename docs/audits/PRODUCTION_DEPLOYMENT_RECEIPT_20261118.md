# Production Deployment Receipt — 2026-11-18 (eb259ee)

## 变更
- 前端研究标注：K 线历史买卖点（研究买点/研究卖点/高波动）+ 当前端 trade_score 锚点。
- 代码提交：分支 `feature/trade-signal-annotations-20261118`，HEAD `eb259ee`。
- 新增 `frontend/src/lib/tradeSignal.ts`、`frontend/tests/tradeSignal.test.ts`；改 `chartAdapter.ts`、`EtfChart.vue`、`Detail.vue`。
- 全程 `research_only / not_calibrated`；不改变规范五档决策、不改变生产策略权重；前端只做服务端指标的阈值映射，不实现金融公式。

## 验证（切流前）
- 独立审核（正确性 + 一致性/合规）：6 项发现，5 项修复（含 HIGH 级 `tradeAnchor` 取 `last.value` 恒 undefined → 改 `last.close`），1 项记录为基线 v0 已知取舍（待 B-c IC 校准）。
- 前端：`vitest` 32 文件 / 259 用例全过；`vue-tsc --noEmit` 干净；`vite build` 成功。
- 后端：`pytest -q` 全量 exit 0。
- 镜像：`china-fund-decision:deploy-eb259ee` 本地构建（镜像内自动 typecheck+build），服务器 `docker load` 成功；镜像内 `workspace-assets/OutlookPanel.vue_vue_type_script_setup_true_lang-ClNsmHdm.js` 含 `tradeSignalPoint`。

## 备份
- `/opt/china-fund-decision/backups/fund_pre_eb259ee_cutover_20261118_001455.dump`（443,740,849 bytes，pg_dump -Fc）。

## 切流
- 项目 `etf-deploy-eb259ee`，compose `/opt/china-fund-decision/etf-deploy-eb259ee/new.yml`，cutover 脚本同目录（含健康检查与失败自动回滚）。
- 旧项目 `etf-deploy-342fa84` 容器已停止并保留（Exited 0/143），镜像 `china-fund-decision:deploy-342fa84` 保留，支持秒级回滚。

## 验证（切流后）
- `api_health=healthy`、`worker_health=healthy`、scheduler Up（`SCHEDULER_ENABLED=false`，与部署前一致）。
- 公网：`/api/health` 200、`/` 200；未认证端点 401/404 符合预期。
- 页面读取：`LocalDisplayReader.read_overview()` 返回 34 只，bundle `sequence=1794913736082`，`generated_at=2026-11-17T11:07:57Z`。
- 线上 chunk 校验：`/workspace-assets/OutlookPanel...ClNsmHdm.js` 200 且包含 `tradeSignalPoint`。

## 回滚
```bash
cd /opt/china-fund-decision/etf-deploy-eb259ee
docker compose --env-file /opt/china-fund-decision/.env -f new.yml down
docker start etf-deploy-342fa84-api-1 etf-deploy-342fa84-worker-1 etf-deploy-342fa84-scheduler-1
```
（cutover.sh 已内置同等自动回滚。）

## 边界
- 资格持续 `UNKNOWN / actionable=false / not_calibrated`；不连接券商、不自动交易；研究标注不构成操作级信号。
- SMTP 邮件推送仍未配置，按所有者指示搁置。
