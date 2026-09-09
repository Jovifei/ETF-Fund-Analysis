# 给本地 Codex：固定代码接收、真实数据与本地部署

现在执行，不重新设计前端、不从旧main重做、不移植旧ZIP。详细任务合同是同仓库 [LOCAL_ACCEPTANCE_V103.md](LOCAL_ACCEPTANCE_V103.md) 的L1–L5，必须逐项执行，不只读完后输出方案。

仓库：https://github.com/Jovifei/ETF-Fund-Analysis.git
分支：fix/v103-history-research-20260909
PR：#31，base为codex/parallel-v102-gapfix-20260908
基线：204a31cbc0214a6e80389224c238bc897b2279af
**固定应用提交：9439563dafc35d7410f9dde39253478a321c96ef**

## 1. 接收和保护

先检查remote/HEAD/脏文件名。在独立clone/worktree接收，保留原E:\project\ETF-Fund-Analysis（路径先核实）及私有配置、原账户、持仓、自选、数据库和报告。不reset/clean/stash/强推。已有库先一致性备份并在副本演练，不能重新init。测试连接不得使用真实库，不在聊天/Git回显凭据或个人内容。

```text
git fetch origin fix/v103-history-research-20260909
git cat-file -e 9439563dafc35d7410f9dde39253478a321c96ef^{commit}
git merge-base --is-ancestor 204a31cbc0214a6e80389224c238bc897b2279af 9439563dafc35d7410f9dde39253478a321c96ef
```

仅在独立目录checkout固定提交，检查每条退出码。之后的纯文档收据可只读获取；应用代码如有后续改动要另审，不自动改变验收SHA。先读AGENTS.md、STATUS.md、HANDOFF.md、docs/README.md、LOCAL_ACCEPTANCE_V103.md及本收据。

## 2. 测试与持久启动

Python3.12、满足engines的Node22.18+；独立环境安装.[dev,market]，前端npm ci。串行执行pytest全量/v103专题、compileall、Vue test/typecheck/build、旧JS、secret scan、diff、临时库Alembic；按workspace-ci执行普通和独立认证Playwright。PostgreSQL条件测试只连接专用临时测试库。失败不得删测试或降低数据门禁。

API与worker同代码同库、重新构建Vue；排除旧进程和源码挂载遮住构建产物。加载原私有配置，不用Mock demo或空新库冒充原数据。已有管理员不重置；仅空库使用安全初始化、用户隐藏输入密码。私有配置显式WORKSPACE_DISCOVERY_ENABLED=false，先手动同步，避免继承别的终端开关。

## 3. L1–L5执行顺序

L1：总览“重算已存历史指标”；补齐510300.SH/512480.SH；下载三指数OHLC；分别同步目录/行业/概念；记录实际数量、源日期、单位、失败类型；重启并断开外部请求验证缓存仍可看。核对磁盘占用，不预设服务器不够。

L2：登录→市场总览原模板→收藏→唯一ETF详情→返回恢复筛选/期限；目录收藏不能误触行跳转，三处自选一致；指数蜡烛图不是点位伪造；缺最新价仍显示历史价格指标；退出清用户状态。

L3：允许按现有模块安装兼容PaddleOCR依赖及模型到仓库外独立目录，私有配置显式OCR_MODE=local_paddle、OCR_LOCAL_MODEL_DIR。先合成图片验证，再本人确认；上传不自动入持仓，缺模型保留手工输入，不上云识别。

L4：允许按scripts/vibe_trial.py安装/验证固定09e8404a33ba0d05e036e01207be4701c61d692c到独立目录，先读CLI帮助；不得换浮动main。本人在隔离CODEX_HOME完成官方登录，不复制全局认证。当前Bridge审查CLI0.149.0，未知版本先审查权限而非删门禁。一次显式预算任务后通过既有导出/候选/审核流，记录耗时、产物和缺失；不启用全市场/定时付费模型。

L5：验证人工复盘保存/修订冲突/用户隔离、白名单因子选择诊断及只读市场历史归档。复盘和因子实验不修改生产权重，旧单位不盲目乘系数。归档不是自动同步运行数据库。

## 4. 不能假称完成的后续功能

网站API Key安全存储、行情包可信重导入/自动双向同步、月度预测、自动反馈训练尚未实现；按文档保留后续开发任务。q code具体产品不明，不声称适配。实源权限不足、OCR模型不匹配和本人登录缺失分别记录，不制造成功。

## 5. 交付和授权边界

给出固定代码SHA、实际本地URL、依赖版本、测试/跳过、实源逐能力统计、重启缓存证明、原模板/指数/收藏截图、OCR/Vibe各自结果和剩余阻塞。详细日志和备份私有，docs只留脱敏摘要。必要集成修复单独提交审核分支，不重写已完成功能。

本次只接收、测试、补本地依赖和本地部署；**不合并main、不移动标签、不部署服务器、不连接券商或自动下单**。可选权限缺失不阻塞合格的日线展示，但不得把health=200或“已配置”当数据成功。
