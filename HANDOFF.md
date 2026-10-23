# 当前工程交接

2026-10-23。目标是网页与后续App共享研究结果：本地F盘存真实数据并定时计算，网站只展示有界结果；账号/持仓隔离，无自动交易。

## 接力要点

- 基线main/origin main：1a4b6652f49c412145d12812fa02820ba0a80991。正式任务固定工作树与原目录分离。
- F:\ETF_Data\ETF-Fund-Analysis 下db/research.sqlite3、state/schedule.sqlite3、outbox分别保存研究数据、执行证据和包/回执。
- 今天新版多槽DELIVERED；最新generation1792738850091 / bundle653164fba9d1ad580478e7211dfddf3f53639a21c27699a37f4fa6395c95fe66，哈希已核，但17:00:27到期。
- 实际阻塞：登录后网页读取超时；15:15/16:10日线失败；两日观察Disabled；尾盘120秒未通过；网页GPT最终复审待完成，连接已恢复。
- 最新授权：独立分支TDD修网站读取与收盘日线，不自动部署；文档“归纳后删除中间文档”单独处理。原目录用户修改、F数据和另一AI服务器备份范围保持。

## 下一动作

先失败复现和根因定位，最小修复并同SHA测试/复审；再验本地生成→签名接收→正常登录总览/详情/K线同批消费。分清报价时间、已结算日线与预测as-of，不能改有效期或资格消除告警。测试不代替实际服务器/手机/自然两日验收。合并与部署按Jovi条件处理，不因health200或accepted自动执行。

核心说明：[README](README.md)、[运行指南](QUICKSTART.md)、[架构](docs/ARCHITECTURE.md)。旧发布收据只证明其固定版本；当前生产镜像/数据库本轮未重新核实。

## 浏览器认证部署契约（必须保留）

生产保持AUTH_ENABLED=true，持久DATABASE_URL不替换成展示库；AUTO_CREATE_SCHEMA=false，HTTPS AUTH_COOKIE_SECURE=true。首次由auth-bootstrap-admin初始化管理员，已有用户/持仓保留，浏览器正常登录。禁止回显凭据。

新一致备份、不可变源码/镜像和回滚材料齐备后才能获准切换，失败受控回退。见 [部署手册](docs/ALIYUN_DEPLOYMENT.md)。资格保持UNKNOWN/actionable=false/not_calibrated。
