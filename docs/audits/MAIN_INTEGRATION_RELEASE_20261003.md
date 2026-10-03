# Main整合与发布接收 — 2026-10-03

## 身份与分支
- 主分支提交 ef287c06b4bd6b8ecd507149a0a0d7bd398e4162，已普通推送origin/main。
- 汇总代码422c5c403d7336d1f7f01307bb99d5b8f2e6f25e；backend/frontend/.github/deploy/scripts无差异。
- 89有效refs中88为汇总分支祖先；全部远端工作已包含。唯一旧本地S2候选c8af982按Jovi选择保留历史，不重复合入。
- 保留原接力文档并提交；仅tasks/todo.md有追加冲突，按Jovi选择保留双方，业务代码无冲突。

## 本轮验证
- Windows完整pytest：1501收集，1478通过，23条件跳过，0失败/错误，630.034秒；JUnit E:/Claude_allow/Download/etf-main-422c5c4-20261003.xml。
- Vue116通过、typecheck/build通过；compileall、Node语法和进度生成check通过。
- 实际Chromium相关回归5通过（中枢日期/结算状态/390px详情）。初次缺少匹配浏览器版本导致启动失败，重用现有Chromium后5通过。
- 精确main CI37129723699运行中；workspace-ci37129723698与audit-platforms37129723696通过。

## 发布边界
- 当前三服务旧镜像38c2c13c，生产健康；DB schema现场核验待完成。
- 源码对照abae131无迁移/依赖更改，本轮image-only保留配置/资格，不启用离线分钟工具。
- 新备份正在独立目录生成；服务器最初1.2GB可用，构建缓存现场Reclaimable6.076GB/Private5.297GB。
- 仅构建缓存清理授权问题待Jovi回复；尚未清理镜像、备份、卷或数据库。
- 已识别实体OnePlus7Pro，按Jovi选择更新线上网页后手机浏览器验收。
- 部署NOT_RUN，真实行情权限/许可/PIT仍UNKNOWN，actionable=false。

现场schema f0e1d2c3b4a5已核实。新备份完成：/opt/china-fund-decision/release-main-ef287c0/backup/fund_decision_20261003_223552_gYRKKQ.sql.gz；343655770 bytes，SHA256 0529d7c0240f2247bd9fa1828040ec77e3aea791c2275246e2fcd136c916ee33，gzip test通过；当前可用818MB。完整CI仍运行、另两条success，镜像未加载。

精确ef287c0三CI全部success：ci37129723699、workspace37129723698、platform37129723696。生产镜像artifact11276792031/397979924 bytes，官方ZIPdigest 5c8a47a56fb42124e2f76163cb7fe9e9eeb634ab273c28b7da687c2274960e9e；本地下载校验中。主分支tree08b61f228d4ff108993efbd9649fd33aa79634e3。switch.sh已补三服务Running及回滚健康/备份SHA与gzip门槛，未执行。

镜像内容身份核验PASS：source ef287c0/tree08b61f2，image sha256:f2b943564736d1e1b6994e5777c834383452a9515cc8f6d3990341b9d4f64bc5；schema f0e1d2c3b4a5，tracked_worktree_dirty=false。内层归档SHA256 8e81dba2880bb061d2e560aacab4386596bb2d6410b5fff68b0ea605f133c12f；ZIP匹配官方digest。release_inventory_complete=false仅因published_image_digest_missing：本轮使用审计CI归档，不声称已发布registry或完整registry收据。
容量核算：新镜像20层，对当前旧镜像无共享diffID；未共享layer tar总876028416 bytes/835.4MiB，当前818MiB余量不足以安全装载，且另需Docker导入临时空间。等待Jovi已发构建缓存清理问题回复；未加载镜像/未切换/手机生产验收NOT_RUN。
