# 当前任务

## 2026-10-24 上下文 availability 类型 P2（接手执行）

- [x] 完整读接手文档、AGENTS/STATUS/HANDOFF、旧全量 JUnit；核 PR51/52/54 最新 SHA 与祖先关系，保留三条原分支和根目录未提交文件。
- [x] 在独立 `codex/context-availability-p2-20261024` 上先写 RED：签名接收、已有自洽坏包、两个 GET 与缺省兼容；原 `b98d683` 上 25 项中 8 FAIL/17 PASS，失败是接收200或 GET500，非测试环境错误。
- [x] 最小修复可选上下文元数据验证：仅显式合法状态可接收，缺省旧包保留；25 项 GREEN，六模块 173 PASS，生产改动限 `local_display_contract.py`。
- [ ] 固定新 SHA，运行 Windows 全量、前端/静态/安全门与精确 GitHub CI；复审差异和收据。
- [ ] 在同一“基金决策”项目的普通 Chat 对新 SHA 作网页 GPT 复审，失败继续修复；全部门槛通过才合 main，先核 Owner 保护清单，不部署。

Review：执行中。旧 bdb556f 与 PR54 b98d683 的既有完整测试收据已核且未重复运行；新 P2 的 RED/GREEN 与 173 项聚焦已留 XML，完整新 SHA/CI/网页复审仍待执行。

2026-10-24。Jovi授权独立分支TDD修读取/收盘刷新、历史接收证明、上下文状态和CI；最终测试与网页GPT复审通过才合main，本轮不部署。文档归纳后删除中间稿；数据、Owner修改、失败与回滚证据保留。

- [x] 核main1a4b665、正式F盘槽/回执及原始超时、收盘失败/过期边界。
- [x] 失败优先修读取/收盘与Vite7.3.7；整合PR53，补签名latest丢失/previous保留P1，135组合通过。
- [x] 版本化上下文时间/状态同代传递；228Vue/类型构建/静态、44Mock smoke、18窄屏、6认证回放通过。
- [x] 原ee6513a完整Windows=2613通过/24跳过/1失败，保留失败；真spawn对照复现重夹具启动超时，仅移测试worker，保留2秒/真进程/无泄漏断言；OCR模块67通过/2跳过。
- [x] 精确清理20份旧Markdown，保留核心结论/合同/NOTICE/测试/失败/回滚；46项文档相关测试已通过，正式阶段计数不晋升。
- [ ] 最终bdb556f完整后端与当前组合精确CI完成；原失败/中断不由局部GREEN覆盖。
- [ ] 同一基金决策普通Chat复审固定候选；通过后合main，Owner原文与未提交状态保留，不自动部署。
- [ ] 正常公网同代消费、真实收盘34覆盖、尾盘120秒、自然两日云端零增长、手机与资格分别验收。

当前结果以[PR52固定候选检查](https://github.com/Jovifei/ETF-Fund-Analysis/pull/52)及[整合审计](../docs/audits/TRUSTED_CONTEXT_INTEGRATION_20261024.md)为准；[正式台账](../docs/PROJECT_PROGRESS.json)的旧PASS不追认本批。
