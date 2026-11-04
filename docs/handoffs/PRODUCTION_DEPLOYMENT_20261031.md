# 生产部署收据 2026-10-31

## 结果

网站切换到提交 8cceba157e38da568478763c66d1de0fc063531e（源码树 5e76dceaf960d886d9eec00793440c3de996d432）的构建镜像。API 与 worker 健康；scheduler 容器运行但 SCHEDULER_ENABLED=false（与切换前一致，计算仍由本机定时任务承担）。数据库由 f0e1d2c3b4a5 升级到 b7c8d9e0f1a2，新增空表 hs300_passive_ratio_snapshots。策略、权重、Provider 选择与账户数据未改动。

## 身份

- 服务器镜像 config 摘要 sha256:3b876da66381f67801bca999dcde44cbc05033a0167e0a90733174f57b1b2149；本机同一镜像的 manifest 摘要 sha256:99ed7b07bc1bcd907b5c3c6687f74af711553598540b3eab51d389aa3c9e7077。两侧创建时间与标签一致，传输 tar SHA-256 为 46885261bcf41a013fc987bf4875939c9d9d33c0414bcedd1a18bcf44a1bdbed。
- 保留旧镜像 sha256:737fe11893d4db9774591768dde28bc50c517701271fdf94cb2b56e4239d8462；旧容器仅停止未删除。

## CI 产物取不到时的替代验证

Actions 在该提交烟测过的镜像产物无法落盘（连接器只给云端引用，匿名下载 401/404，本机 gh 未登录）。改为按同一 Dockerfile 与同一源码树重建，并复跑 CI 对镜像做的检查：alembic upgrade head 到 PostgreSQL 16.15、/api/health ok 且 auth_enabled true、scripts/workspace_image_smoke.py 通过、alembic check 无待办变更、展示包模式下只读研究接口返回 unavailable/research_ratio_not_published 且 research_only=true/actionable=false/qualification=UNKNOWN。服务器演练用真实备份副本：44 张表恢复成功后新版升级到 b7c8d9e0f1a2，三个服务健康，未认证 401。

依赖偏差：pip 自由解析给出 akshare 1.20.16，该版本使镜像内腾讯历史通道测试失败；1.20.2 才是本次提交所针对且 CI 与本机全量通过的版本，故在已验证镜像上追加一层固定 akshare==1.20.2 并复跑同批测试通过。pyproject 未固定该依赖，留作后续独立决策。镜像内完整 pytest 另有若干失败，全部源于读取未打包进运行镜像的 docs/、README、deploy/、frontend/tests、.git 路径，与代码行为无关；全量权威证据仍是 CI 主机运行与本机运行。

## 配置与回滚

原 Compose 链 12 个文件已被此前清理删除，无法证明重建等价，因此改为按运行容器观测规格重建并逐项核对：new.yml 的 command、user、working_dir、init、只读根、cap_drop ALL、no-new-privileges、重启策略、两个 tmpfs、四个绑定挂载（含只读身份登记表）、端口、网络与三个健康检查全部一致，应用环境变量集合摘要一致 e454167d71f3c88d；仅基础镜像的 PYTHON_VERSION/PYTHON_SHA256 因上游补丁不同而变化。

.env 中 APP_VERSION、MARKET_PROVIDER、REGISTRATION_ENABLED、SCHEDULER_ENABLED 四个值与线上实际运行值不一致；若沿用会把数据源换成 akshare、开启放置注册并双开调度器，因此生成器一律取线上真实值固定，疑似密钥项出现同类偏差则拒绝生成。.env 本身未修改。

回滚：生产三个旧容器 ReadonlyRootfs=true 且迁移目录无独立挂载，直接重启旧容器在迁移后会因不认识新 revision 退出 255，所以 rollback.yml 用只读挂载 b7c8d9e0f1a2 迁移文件的方式启动旧镜像。该路径已在真实数据副本上验证：旧镜像在 b7 库上健康启动，45 张表与新表数据保留，未认证 401，无破坏性降级；新表非空或序列状态异常时守卫拒绝降级。

## 数据保护

切换前新备份 /opt/china-fund-decision/backups/fund_pre_8cceba1_cutover_20261030_232640.sql.gz 为 430316826 字节，先发布校验和再发布归档，独立 sha256sum -c 通过，gzip 完整性与 pg_dump 收尾标记校验（该版本收尾为 backslash-unrestrict，不是旧版注释）。更早的 11:48 备份与服务器 8 份历史 fund_pre_* 备份均未删除。演练使用独立项目、网络、目录与副本库，未绑定生产端口或数据目录。holdings=0、auth_users=3、user_watchlist_entries=6 切换前后一致。

## 已知问题

- 演练期间在同一台 1.8 GiB 内存服务器上同时跑副本恢复与两套栈，触发系统级 OOM，内核杀掉了同机 star-photo-star-weather-1；该容器自动重启后恢复 healthy，ETF 生产容器与数据库未受影响。后续不再在此机并行此类负载。
- 生产 API 容器 23:14 记录一次退出码 0 的重启（容器 ID 与创建时间未变，仅重启），原因未定位，保留收据。
- 仓库 visibility=public，与既往“私有”记录不一致，未改可见性。
- 早前出现在工具记录中的同步凭据尚未轮换，需本机与服务端配套处理。
- 邮件仍未配置，无真实投递证据；项目 Hub 本机连接被拒绝（WinError 10061）。
- HS300 清单仍 provisional，占比任务未排定，生产卡片继续显示未完成校准与未知资格，不产出可操作信号。

## 切换后即时核验

- 新镜像容器挂载与线上原规格一致（四个绑定挂载、身份登记表只读），API 与 worker 自启动以来日志无 traceback 或错误行。
- 新镜像可读活跃展示包指针：latest.json 含 46 条接收历史，最后 sequence 1793353846919，引用的 bundle 文件存在。
- 该指针 generated_at 为 2026-10-30 17:49（本地），有效期两小时，至 00:25 已到期。按既有规则到期包仍可读取并标记历史，因此夜间网站显示"今日数据加历史标记"属预期行为，有效包由下一交易时段推送产生。
- 未强制夜间重推旧数据来冒充新鲜数据。升级后接收端对新包的接收仍有待下一时段自然验证。
