# Production Deployment Receipt — 2026-11-19 (e542273, main)

## 变更
- 部署 `main`（2026-11-18 合并结果）：研究标注（K 线买卖点 + trade_score）+ UI 显示修复（1827e79）。
- main 提交：`1578e1a`（trade-signal + 收据）→ `5575395`（显示修复）→ `e542273`（合并记录）。
- 前端构建哈希与本地 main 一致：`workspace-assets/index-CC4X85TY.js`、`OutlookPanel...-CEbd_kTv.js`（含 `tradeSignalPoint`）。

## 验证（切流前）
- 合并后全量验证：vitest 33 文件/270 用例、`vue-tsc --noEmit` 干净、`vite build` 成功、`pytest -q` 全量 exit 0。
- 备份：`/opt/china-fund-decision/backups/fund_pre_e542273_cutover_20261118_233617.dump`（443,740,951 bytes，`pg_restore -l` TOC 463 项校验通过）。

## 切流
- 项目 `etf-deploy-e542273`，compose `/opt/china-fund-decision/etf-deploy-e542273/new.yml`，cutover 脚本同目录（健康检查 + 失败自动回滚）。
- 旧项目 `etf-deploy-eb259ee` 容器已停止并保留（Exited 0/143），镜像 `china-fund-decision:deploy-eb259ee` 保留，支持秒级回滚。

## 验证（切流后）
- `api_health=healthy`、`worker_health=healthy`、scheduler Up（`SCHEDULER_ENABLED=false` 不变）。
- 公网：`/api/health` 200（连续 3 次）、`/` 200；未认证端点 401/404 符合预期。
- 页面读取：`LocalDisplayReader.read_overview()` 返回 34 只；当前 bundle `sequence=1794995377359`。
- 线上资源：`/workspace-assets/index-CC4X85TY.js` 被首页引用；`OutlookPanel...-CEbd_kTv.js` 200 且含 `tradeSignalPoint`。

## 回滚
```bash
cd /opt/china-fund-decision/etf-deploy-e542273
docker compose --env-file /opt/china-fund-decision/.env -f new.yml down
docker start etf-deploy-eb259ee-api-1 etf-deploy-eb259ee-worker-1 etf-deploy-eb259ee-scheduler-1
```
（cutover.sh 已内置同等自动回滚。）

## 边界
- qualification UNKNOWN / actionable=false / not_calibrated；不连接券商、不自动交易；研究标注不构成操作级信号。
- SMTP 邮件推送仍未配置，按所有者指示搁置。