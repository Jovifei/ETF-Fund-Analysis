# v1.0.3 本地接收与尚未执行的验收

应用基线：204a31cbc0214a6e80389224c238bc897b2279af；修复分支：fix/v103-history-research-20260909。最终接收使用交付 Prompt 的固定 SHA，而不是旧 main 或临时集成提交。只做本地接收、复测和部署；生产另行批准。

## 接收保护

先检查 remote/HEAD/脏文件名，独立 clone/worktree；不 reset/clean/stash，不覆盖原工程。不迁入旧 ZIP。保留仓库外私有配置、原账户、数据库、持仓、自选与报告；已有库先备份并在副本演练。测试仅用临时库，不能把 TEST_POSTGRES_URL 指向用户数据库。不回显凭据和个人内容。

Python3.12、满足 engines 的 Node22.18+；按 pyproject.toml 安装 dev/market，npm ci。执行 pytest 全量、compileall、Vue test/typecheck/build、旧JS、secret scan、git diff --check、临时 SQLite Alembic upgrade/check。PostgreSQL 条件测试用专用可销毁测试库。按 workspace-ci.yml 分别执行普通 Playwright 和 playwright.auth.config.ts。串行运行后端测试，避免既有共享SQLite夹具被另一pytest进程清掉。

## L1 实际行情与指数：需要本人配置/网络

先确认运行的 API 与 worker 使用同一固定版本、同一持久库及有效 Provider；不把 Mock demo 当原数据部署。不重新 init 已有库或重置管理员。

1. 先在总览点“重算已存历史指标”，查看任务各步与原版表。已有OHLC但缺量仍能看价格指标，错误标的不得阻断其他基金。无历史不能造数。
2. 详情显式点“补齐历史并加入研究池”，先测试510300.SH、512480.SH；加入自选后在三处收藏状态一致。已有缓存不能被一次下载失败删除。核实实际下载日期/数量/单位，保留旧单位修复边界。
3. 点击总览指数卡片后点“下载指数历史”，核验cn-shanghai-composite/cn-csi300/cn-csi-all对应注册表实际context_id（以API为准），三只真实OHLC入库后卡片点数和涨跌与最新缓存一致。当天缺实时数据标最近收盘，不能拼造当日点数。
4. 分别同步目录、行业、概念；统计返回/入库/覆盖日期和失败原因。不将目录数当交易所全量证明，不自动计算所有目录基金。GET页面不抓行情。
5. 两标的与三指数完成后重启API/worker，断开外部数据请求再验证旧K线和日期仍可读取。记录磁盘实际占用，不预设磁盘不足。

## L2 图表与交互

真实HTTP浏览器验证：登录→总览原模板→收藏→同一ETF详情→返回保留筛选/期限；目录收藏不触发行跳转；取消收藏跨页面同步；退出清旧状态。指数卡片打开实际蜡烛图，OHLC不是复制收盘价；缩放、平移、十字线、重置可用。已有历史无最新报价时K线/MA/MACD/KDJ/RSI依然存在。原板块、持仓、搜索、账户注册流程不得回退。测试数据截图明确标Mock，不能当真实行情。

## L3 本地OCR：可选，需依赖与模型

live runner 允许私有配置 OCR_MODE=local_paddle 与已存在的绝对 OCR_LOCAL_MODEL_DIR；默认disabled。安装项目ocr可选依赖，并按既有OCR模块要求预下载适配模型到仓库外目录。只有目录存在不代表模型可用。不得在普通GET触发下载；不上传真实持仓图至云模型。先用合成图片验收超时/临时文件清理/字段预览/人工确认，随后本人图片逐项确认代码、份额和每份成本。缺模型如实保留手工输入，不伪报OCR成功。

## L4 本地Codex与Vibe：本人登录，单次有预算

AI研究页已有配置指引、设备设置链接、建立任务、导入及审核。Bridge关闭时仍可导出证据包。只为独立试点启用，不自动开启全市场或定时模型任务。

Bridge 当前审查CLI为0.149.0；先读 bridge/etf_agent_bridge.py 的 --help 与安全检查。`--root <独立目录> doctor` 后，按实际隔离目录 `<root>/runner-home/.codex` 设置 CODEX_HOME，让用户在本机完成官方登录，不复制全局auth.json。核对版本；未知版本先复核能力开关，不删除版本门禁。

管理员启用WORKSPACE_BRIDGE_ENABLED后，在设置生成设备配对码；本地 `pair --origin <站点>`，随后 `claim`，按预算 `run-codex <job-id> --model <明确模型>`，`submit <job-id> <result.json>`。以CLI实际帮助为准，凭据通过安全输入，不作命令行明文。确认返回待审核候选，设备不能发布或改策略。网址若为HTTP只允许回环，本地主动连接云端时HTTPS，不反向连接用户电脑。

Vibe独立试点：

```bash
python scripts/vibe_trial.py doctor --root <新的仓库外Vibe目录>
python scripts/vibe_trial.py install --root <同目录> --allow-network-install --max-minutes 30
python scripts/vibe_trial.py verify --root <同目录> --max-minutes 30
```

固定09e8404a33ba0d05e036e01207be4701c61d692c；不要改为浮动main。安装/源码验证不调用模型。API/UI按该版本README绑定回环，产品数据和Codex登录同样用trial-runtime隔离目录。一次真实研究由用户官方登录后显式运行，分别记录耗时、用量、产物与缺口；公司深研不直接冒充ETF研判。用既有 bridge/export_vibe.py（先读 --help）转换产物，在外部研究包界面预览、导入、审核。禁止整个.local上传或直接访问主站数据库。

本网站直接保存模型API Key尚未实现安全Secret Store，因此不开放；外部模型结果可先通过已有研究包导入。用户说的“q code”具体产品未确认，不宣称支持。

## L5 人工复盘、因子与离线归档

/review 保存当时判断、后续结果、待检验建议，日期选择/刷新持久、修订冲突409、不同用户隔离。它绑定保存时快照，不假称早先已知。AI候选报告仍独立审核；不让人工笔记直接改生产权重。

/factors 从白名单选最多12个因子提交诊断；检查选择字段、覆盖率和1/3/5/10结果，不生成新预测概率，不自动启用因子。一个月、自动反馈训练与参数择优上线仍待研究验证。

归档命令与容量边界见 [历史存储](HISTORY_STORAGE_V103.md)。只导出显式市场数据到新私有目录，核验哈希、无凭据/持仓和重复目录拒绝。本版没有通用行情包重导入或自动双向同步，不能同步运行中的数据库。

## 验收记录

输出固定代码SHA、实际本地URL、依赖版本、测试/跳过/失败，Provider按能力真实记录、缓存重启证明、原模板/指数/收藏截图、人工复盘与因子结果、可选OCR/Vibe各自状态。详细日志私有保存，docs只留脱敏摘要。失败不删测试、不放宽资格，不自动切付费API。可选权限或模型缺失不阻塞已通过的日线产品；无法完成的项目给出具体原因及复现命令。
