# 本机与服务器数据位置、磁盘核账（2026-10-25）

本次只读统计文件元数据与数据库聚合，未读取账户明细、删除文件或修改数据库。容量是检查时点值；`du` 的 GiB、数据库字节数和 Docker 共享层不能直接逐项相加。

## 活跃数据链路

生产 `WORKSPACE_RESEARCH_SOURCE=local_bundle`、`SCHEDULER_ENABLED=false`；本机 `ETF-Local-Live-Compute` 的工作树在 E 盘，数据根参数指向 `F:\ETF_Data\ETF-Fund-Analysis`。网站消费服务器上的有界展示包，账户/收藏仍在服务器 PostgreSQL。

| 只读聚合 | 本机 F 盘研究库 | 服务器 PostgreSQL |
| --- | ---: | ---: |
| `daily_bars` | 68,962 行，52 标的，最新 2026-10-23 | 22,327 行，35 标的，最新 2026-10-09 |
| `quote_snapshots` | 2,980 行，52 标的，最新 2026-10-23 | 15,513 行，35 标的，最新 2026-10-09 |
| `holdings` | 0 行 | 0 行 |

因此本机有较新的原始行情；服务器仍保留旧行情和大量旧研究结果，不能说服务器完全没有原始数据。云端数据库逻辑大小 845,618,199 字节（约 806 MiB），其中 `decision_board_snapshots` 约 693,501,952 字节（约 661 MiB）；PostgreSQL 磁盘卷约 1.6 GiB。生产展示包目录 19 个文件、242,889,675 字节（约 232 MiB），配置上限 335,544,320 字节（320 MiB）。

## 本机 F 盘

`F:\ETF_Data\ETF-Fund-Analysis` 共 3,995 个文件、约 20.79 GiB：`server-archives` 10.29 GiB、`backups` 7.73 GiB、`outbox` 1.41 GiB、`db` 0.88 GiB，其余约 0.48 GiB。这里的大头是本机归档/备份，不能把整个 20.79 GiB 称为活跃行情库；检查时 F 盘尚余约 293.9 GiB。

## 服务器备份与 40 GiB 磁盘

`/opt/china-fund-decision/backups` 有 8 个文件、合计 1,672,718,281 字节（约 1.56 GiB）。主体是 v1.0.6、v1.0.7、v1.0.9 发布前的三份完整数据库快照（各约 444 MB）及 10 月 2 日旧 SQL 压缩备份（约 342 MB）；另有约 4 KB 的持仓结构备份和校验文件。它们供发布失败恢复使用，平时不加载为 RAM；目前没有擅自清理或设定删除策略。

服务器根盘 40 GiB，检查时约 28 GiB 已用、10 GiB 可用。只读目录核账：Docker 根目录约 13 GiB（`overlay2` 镜像/容器层 8.6 GiB、卷 3.6 GiB、容器与构建缓存各约 193 MiB）；非 Docker 文件约 15 GiB，其中 `/opt` 4.5 GiB（ETF 项目约 2.2 GiB，含上述备份）、`/usr` 4.4 GiB、两份根目录 swap 文件合计 4 GiB，其余系统/用户目录约 2 GiB。Docker 卷含 ETF PostgreSQL 和其他项目；共享镜像层不能全算作 ETF 行情数据。

服务器 RAM 总量约 1.8 GiB，检查时可用约 452 MiB，swap 约 628 MiB 已使用；三个 ETF 容器曾测得合计约 389 MiB。磁盘上的 20.79 GiB 本机文件未整体进入服务器 RAM。服务器内存余量偏小、磁盘尚余约 10 GiB，后续应审计旧备份与镜像保留策略；任何删除必须先核回滚与归属，不从本收据自动执行。
