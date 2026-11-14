# 生产部署收据 2026-11-14（129840e，us-markets 整合 A 档）

## 结果

网站切换到 `integrate/us-markets-20261114` 分支 tip `129840e`（+ C 档测试常量提交 `11071fe`）的本机构建镜像 `china-fund-decision:deploy-129840e`。**A 档 = 只上网站**：生产者身份、登记表、ECS 身份 env、生产任务全部不动。**零迁移**（分支 alembic head = 生产库 = `b7c8d9e0f1a2`）。api/worker healthy，scheduler running（`SCHEDULER_ENABLED=false` 不变）。策略、权重未改动；structure_v1 三列修复与可选包分片随本镜像上线；美股卡片按设计显示诚实空态（`US_MARKETS_RESEARCH_SNAPSHOT_PATH` 由 B 档生产者侧提供）。

## 前置门（全部通过后才切换）

- **ECS 身份门**：运行中 api 容器 `SHADOW_SYNC_CODE_SHA=98ba055f6e5be99ff949e62822b9714c7ec1894c`、`SHADOW_SYNC_CONFIG_HASH=9efe8845e2e26406de22b30b08d0697f3c52b979f6d3e06b7a1398bcca21285b` —— 与报告期望、登记表末条（4 条链 `dcffa8e→c39ab09→a0d52e4→98ba055`，approved 2026-11-10）、11-13 accepted 包完全一致。
- 分支 `129840e` 部署定义与 main 零差异（deploy/、Dockerfile、compose）——另一执行人 Xfei DeepSeek 预检结论，本次复核采纳。
- 候选镜像 `etf-candidate:129840e`（manifest `sha256:33dd8080…`）由预检构建并冒烟通过；本会话在其基础上先做 C 档再重建。

## C 档（测试常量对齐，随本次一并完成，owner 授权"把工作做完"）

- `backend/tests/test_bundle_identity_registry.py:11-12`：`a0d52e4…/a12c6ea1…` → `98ba055…/9efe8845…`（取值 = 登记表末条 = ECS env = 11-13 accepted 包，三方一致）。
- 分支提交 `11071fe`（129840e 之上），focused test 绿；已推送 `origin/integrate/us-markets-20261114`。
- 部署镜像从 **分支 tip `11071fe`** 构建（非预检的 129840e），差异仅为该测试常量提交。

## 备份

- `/opt/china-fund-decision/backups/fund_pre_129840e_cutover_20261114_230835.dump`，443,740,463 字节，`sha256 7756b29668c1456cb78a1356a78a57194faff37754b06de792d23c991fe4f463`（`.sha256` 同目录），TOC 478 条。
- 未删除任何历史备份。磁盘 40G 用 85%（6.6G→切后 5.9G 可用），保留策略仍需 owner 授权。

## 镜像内验证（切换前）

- `akshare 1.20.59`（又一次自由解析漂移）：腾讯历史测试 **11 passed** —— 守卫修复持续有效，无需钉层。
- 镜像内 `alembic heads` = `b7c8d9e0f1a2`。
- 沙盘演练（独立网络/PG 副本/独立端口）：API production 模式 healthy，`auth_enabled=true`，`workspace_image_smoke.py` 全过（Vue 深链/CSP/immutable 资产/私有 API/404）。

## 切换与即时核验

- 编排：`/opt/china-fund-decision/etf-deploy-20261114/new.yml`，由 `etf-deploy-20261110/new.yml`（现行生产规格）派生，**diff 仅两行**（项目名 `etf-deploy-129840e`、镜像引用）；身份三件套（`GIT_COMMIT_SHA`、`SHADOW_SYNC_*`=98ba055/9efe8845）保持不变——它们描述生产者，与网站镜像无关（沿用 10-31/11-08 先例）。
- 传输：本机 `docker save | gzip | ssh docker load`；服务器载入 ID `521db6b57ad8`（909MB，与本地 manifest-list ID `c2bdc28d…` 的差异为 load 平台化行为，同一 save 流）。
- cutover 脚本内置回滚：候选 unhealthy → `compose down` + `docker start` 旧容器。
- 即时核验：api healthy（restarts=0）、worker healthy、`health_json` ok（v1.0.13/production/public_composite/auth_enabled=true）、未认证 holdings 401、**新容器身份 env 断言 = 98ba055/9efe8845 精确匹配**。
- 公网 `https://etf.joviluma.com/`：200（0.51s）；health 同上；未认证 401；CSP 保持。
- 日志：api/worker 自启动以来 0 error/traceback。
- 展示包指针 `/app/.local/display-v113-a0d52e4/latest.json` 可读，接收历史完整；未手改任何包文件。

## 已知问题（预存，非本次引入，均已核实在 main `1c0fd6d` 上同样失败）

1. `backend/tests/test_structure_weight_replay.py` 多个用例在 Windows 检出环境失败：代码抛 `frozen_formula_source_changed_review_required`（冻结公式源校验先行）而测试期望 `source_code_identity_mismatch`。高度疑似 CRLF 检出改变公式文件哈希所致（CI ubuntu 绿）。语义裁决（改代码顺序还是改测试期望）留 structure 工作负责人。
2. `backend/tests/test_historical_archive.py::test_store_refuses_overlap_and_symlinks[symlink]`：Windows 符号链接权限所致。
3. 服务器磁盘 85%（5.9G 可用）：多轮部署镜像 + 备份并存，保留策略需 owner 授权。
4. 美股卡片为诚实空态（设计内）；B 档（生产者切 129840e 出真数据）未执行，等 owner 单独批准。

## 回滚

零迁移，回滚 = 恢复旧栈：

```bash
cd /opt/china-fund-decision/etf-deploy-20261114
docker compose --env-file /opt/china-fund-decision/.env -f new.yml down
docker start etf-deploy-98ba055-api-1 etf-deploy-98ba055-worker-1
```

旧镜像 `china-fund-decision:deploy-98ba055` 与三容器停止保留；数据库无变化，旧镜像直接可读。
