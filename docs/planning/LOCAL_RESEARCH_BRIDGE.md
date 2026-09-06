# 本地研究工作站 → ETF 网站：桥接合同草案

2026-09-06，`research-package/v1` 设计草案；**接口、连接器、调度均未实施**。关联 [总方案M3–M5](ETF_WORKSPACE_VNEXT.md)。

## 1. 角色与信任边界

```text
本地：隔离Vibe/Codex工作区
  受控数据采集 → 确定性计算/证据 → AI解释 → 本地候选产物
                                              ↓
独立Connector：白名单选择 → schema/hash/隐私检查 → 仅出站HTTPS
                                              ↓
云端FastAPI：鉴权/幂等/隔离 → 候选区 → 人工审核 → 网站研究档案
                                              ↓
              与已有ETF/板块/持仓关联（不改权威行情/动作）
```

生产分析模型继续遵守 AGENTS：没有Shell、任意网络、数据库写入或券商工具。将来本地研究器需要工具时，必须在独立ADR中批准受控采集/计算白名单；与主站进程、凭据、数据库彻底分离。优先使用受控MCP或外部采集器，不让模型任意执行本机命令。不能把原项目 AGENTS/Skill 全文覆盖到我们的安全合同。

本地部署≠本地模型推理：Codex/API模式通常仍需联网调用服务，数据传出范围、预算和服务条款必须单独确认。无 GPU 可先评估托管模型，但不承诺无费用/无限额度。

## 2. 选择Vibe的具体原因与适配边界

已读固定提交 `09e8404a33ba0d05e036e01207be4701c61d692c` 的 `orchestrator/src/run.ts` 与 `runner.ts`：CLI输出run_id/run_dir/status/stage状态；退出码0=complete、2=incomplete或stale、3=failed；SDK每run一个thread、每stage一个turn，事件日志与超时/隔离已有实现。

README描述的report.md、evidence.json、calculations.json、conflicts.json、manifest.json适合转换为研究包；viewer.html不直接发布到主站。**六阶段CLI合同不代表日报/产业雷达等所有入口拥有同一产物格式**，每种任务均需适配器和fixture测试。

现有 `backend/app/services/review_service.py` 支持严格ReviewMemo、证据ID、风险/限制、hash和runner白名单，值得复用。但它目前只允许既定review runner，且摘要/集合有大小限制；不是通用外部研究仓库。需要新增受审查的artifact接收层并关联候选，不伪装runner名称、不硬塞长研报。

## 3. 网站中的AI配置分三种模式

| 模式 | 用户体验 | 凭据边界 |
|---|---|---|
| 不启用AI | 图表/指标/持仓/已有报告仍可用 | 无模型凭据 |
| 托管API | 选择provider/model、填自己的API Key、测试、撤销 | HTTPS写入；后端按owner加密；返回仅掩码和状态 |
| 本地Codex研究器 | 配对本地设备，显示在线/最后成功任务；选择本地任务 | 官方登录留在本地CODEX_HOME/系统凭据库；网页不索要auth.json/Cookie |

模型Key、行情Token、网站会话Cookie、研究上传凭据是四类不同凭据，不可互换。任务只含`credential_ref`，模型看不到原始Key。普通用户不能读取管理员或他人的连接。自定义Base URL需防SSRF：明确允许源、阻断内网/元数据地址及重定向绕过；本地模型地址由本地受控配置解释，不交给公网服务随意抓取。

Codex官方文档支持 `codex exec --json`、`--output-schema`、SDK线程管理及本地认证；Vibe支持的版本要依其固定依赖另行资格测试。自动化优先考虑可轮换的适用凭据方式，不能因为用户有ChatGPT订阅就假定可无限后台运行或把订阅凭据给网站。参考：
- https://developers.openai.com/codex/noninteractive/
- https://developers.openai.com/codex/auth/
- https://developers.openai.com/codex/sdk/

## 4. 研究包（字段建议，不是现有API）

| 字段 | 规则 |
|---|---|
| schema_version / package_id / run_id | 版本固定、唯一标识；重传不能复制任务 |
| producer | 项目、精确commit、adapter版本、Skill版本、模型ID；不包含密钥/本机用户名 |
| task_type | market_review / etf_research / news_digest / catalyst_watch / report_review / factor_diagnostic |
| instruments | 内部规范代码、交易所、asset_type；转换.SH/.SS显式登记 |
| as_of / generated_at / timezone | 证据截止、生成时间分开；Asia/Shanghai或显式offset |
| source_status / completeness | complete、incomplete、stale、failed与缺失原因 |
| input_snapshot_ids / input_hash | 固定输入，避免“最新”指向运行途中不同快照 |
| evidence | 来源标识/URL、published_at、available_at、retrieved_at、hash、简短授权摘录 |
| claims / conflicts / limitations | 每个判断关联证据；事实、推断、反证分开 |
| artifacts | 仅批准类型、大小、相对路径、MIME、SHA256；禁止任意绝对路径 |
| usage | 调用数、耗时、用量；未知费用保持null，不冒称0 |
| privacy_class | public_market / personal；owner由认证映射，不信任包内user_id |

外部建议只能存`external_opinion`。禁止包直接修改IndicatorSnapshot、ForecastSnapshot、SupportResistanceSnapshot、canonical action、持仓或策略参数。外部“买入”不会自动变成系统“可入场”。新闻/财务事实进入主数据需另一条有来源审计的规范化流程。

## 5. 传输、状态与失败处理

**第一版**手动上传批准的研究包，用户选择所属任务/标的并确认。**第二版**独立Connector用范围受限的可撤销设备凭据，只向主站允许的接收地址推送。生产不公开Vibe的本地API，不让浏览器直接跨源访问localhost，不共享SQLite/PostgreSQL，不上传整个.local目录。

建议将来端点（均待实现）：`POST /api/research/imports` 接收；`GET /api/research/imports/{id}` 查状态；人工`publish/reject`。设备上传权限不含发布权限。可选以后本地主动轮询“声明式任务”，只允许task_type、合法代码、预算，绝不接收Shell字符串、插件URL或任意脚本。

状态：queued → running → completed/incomplete/failed → validated → pending_review → published/rejected；stale作为数据资格独立字段。complete只表示上游执行结束，不等于证据有效/预测已校准。

幂等键至少绑定owner、producer、run_id、artifact hash；同run同hash重传返回旧结果，同run不同hash拒绝或产生显式revision。接收有上限、限流、签名或受认证hash清单、过期与防重放；不能只凭SHA256判断发送方可信。原子写入和确认回执，Connector指数退避、断点续传、有最大次数；云端发布使用单调版本，迟到旧报告不覆盖较新报告。

无联网/电脑关机：显示本地离线及最后成功时间。费用耗尽：标blocked_budget。任务失败：保存脱敏原因，不用旧报告冒充新报告。用户撤销：终止后续采集/上传并可撤销发布。

## 6. 数据与渲染安全验收

禁止提交.auth/.env/Cookie、完整日志、数据库、账户号和原始持仓截图。个人持仓进入外部模型需按任务显式授权；默认公共市场分析不带持仓。

Markdown经净化渲染；禁原始HTML/script、外部自动资源、任意iframe。研报全文上传还须考虑版权/数据商许可；先同步元数据、引用和有权使用的摘要。压缩包防路径穿越、符号链接、解压炸弹和总大小超限。引用不自动打开为可信指令。

最小测试：空包/未知版本/未来as_of/缺来源/hash篡改/过期重复/同run冲突/跨用户/脚本注入/退出码2与3/设备撤销/预算上限/个人数据误分享。保留输入hash、审批人、审批时刻、发布revision、回滚事件。

## 7. 尚需在实施前确认

本机OS、CPU/RAM/磁盘、开机时段、可用模型及预算；不需要在聊天中给密钥。M3先隔离运行一份样例、记录资源与产物；M4再做手动导入；全部稳定且获授权后才加入定时。当前没有任何本地研究器已由本轮部署。
