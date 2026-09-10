<script setup lang="ts">
import {ref} from 'vue'
const mode=ref('api')
const powershell=String.raw`# 在项目根目录的 PowerShell 执行；这是隔离的本地研究目录。
$root = 'E:\AI_Tools\Other\ETF-Agent-Bridge'
New-Item -ItemType Directory -Force "$root\runner-home\.codex" | Out-Null
$env:HOME = "$root\runner-home"
$env:USERPROFILE = "$root\runner-home"
$env:CODEX_HOME = "$root\runner-home\.codex"
codex login
python bridge/etf_agent_bridge.py --root $root pair --origin http://127.0.0.1:8082
python bridge/etf_agent_bridge.py --root $root doctor
# 替换下面模型名为你账号有权使用的模型；只运行1个任务。
python bridge/etf_agent_bridge.py --root $root work --model YOUR_MODEL_ID --max-jobs 1 --max-minutes 10`
</script>
<template><section class="card section" data-testid="ai-setup-guide"><div class="card-header"><h2>如何开始 AI 研究</h2></div><div class="card-body"><div class="segmented ai-mode-cards" role="group" aria-label="AI连接方式"><button class="mode-card" aria-label="模型 API" :class="{active:mode==='api'}" :aria-pressed="mode==='api'" @click="mode='api'">模型 API<small>复用已保存配置</small></button><button class="mode-card" aria-label="本地 Codex" :class="{active:mode==='codex'}" :aria-pressed="mode==='codex'" @click="mode='codex'">本地 Codex<small>隔离设备执行</small></button><button class="mode-card" aria-label="不用 AI" :class="{active:mode==='manual'}" :aria-pressed="mode==='manual'" @click="mode='manual'">不用 AI<small>保留确定性研究</small></button></div>
<div v-if="mode==='api'" data-testid="ai-mode-api" role="tabpanel"><h3>模型 API · 共用配置</h3><ol class="ai-step-list"><li>打开 <RouterLink to="/settings">设置与连接 → 模型 API 连接</RouterLink>，新增服务地址、Key与模型，设为本人默认配置。</li><li>勾选费用确认，测试一次；失败按提示检查服务权限、Key、模型和worker。</li><li>回 ETF 分析或每日复盘，点击“建立证据包与任务”。证据包就是这次分析使用的行情、指标、新闻清单，不是另一份模型配置。</li><li>选择任务，在“用已保存的模型分析这份证据”选择配置并确认费用。等待工作器返回报告，再审核。</li></ol><p>ETF与每日复盘使用同一份个人配置，不必重复填写。网页不会因为打开研究档案就再次调用模型。</p></div>
<div v-else-if="mode==='codex'" data-testid="ai-mode-codex" role="tabpanel"><h3>本地 Codex · 隔离执行</h3><ol class="ai-step-list"><li>本机安装官方 Codex CLI 和本项目依赖；使用独立目录，不能复制全局 auth.json。</li><li>API服务私人配置启用 <code>WORKSPACE_BRIDGE_ENABLED=true</code>，重启服务；网页“设置 → 隔离研究设备”生成一次性配对码。</li><li>在本机新 PowerShell 执行下方命令。官方登录由你本人完成；pair时在终端输入配对码。服务不在8082时改成你的实际HTTPS地址，不要关闭证书验证。</li><li>网页建立研究任务，然后执行一次work。报告回传后在研究任务查看和审核。doctor仅检查桥接，不等于模型账号已登录。</li></ol><pre class="report-text">{{powershell}}</pre><p>本项目会检查 Codex 版本与工具隔离。出现 unreviewed_codex_version 时按 bridge 文档审查版本，不删除门禁。每天自动运行应在一次真实任务验证后另行启用。</p><p>Vibe 的深度研究属于独立可选适配，先按 <code>docs/LOCAL_ACCEPTANCE_V103.md</code> 与实际安装脚本 --help 固定版本隔离验收，不直接给它生产数据库凭据。</p></div>
<div v-else data-testid="ai-mode-manual" role="tabpanel"><h3>不用 AI · 确定性研究</h3><p>图表、价格指标、自选、持仓与人工复盘都能直接使用。每日复盘先写自己的判断和后续结果，待验证的参数建议不自动进入生产。</p></div><p class="small-note">通常不需要另外搭建 MCP。本站已提供固定证据、任务领取与结果回传；需要让其他AI主动检索站内数据时，再增加经授权的只读接口。</p></div></section></template>
<style scoped>.ai-mode-cards{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;margin-bottom:16px}.mode-card{display:flex;flex-direction:column;align-items:flex-start;gap:4px;text-align:left;border:1px solid var(--border);border-radius:8px;background:var(--surface);padding:10px 12px;color:var(--muted);cursor:pointer}.mode-card small{font-size:11px;color:var(--muted)}.mode-card.active,.mode-card[aria-selected="true"]{border-color:var(--accent);background:rgba(59,202,207,.1);color:var(--text)}.ai-step-list{padding-left:24px;line-height:1.7}.ai-step-list li+li{margin-top:8px}@media(max-width:700px){.ai-mode-cards{grid-template-columns:1fr}}</style>
