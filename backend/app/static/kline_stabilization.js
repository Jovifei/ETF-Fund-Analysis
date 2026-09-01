'use strict';

/**
 * K线企稳分析看板
 * 数据源：后端 /api/workbench/kline/summary（TD九转/形态预测/缠论均由后端计算）
 * fallback：API 不可用时回退到内置静态快照（2026-08-31 盘中v4），保证页面可独立预览。
 */

const $ = (sel) => document.querySelector(sel);
const esc = (s) => String(s ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');

// ============ 静态 fallback 数据（与后端结构一致） ============
const STATIC_DATA = {
  meta: {
    title: 'K线企稳分析看板 · 盘中实时v4（16标的）',
    subtitle: '16标的 · 场外基金关联分析 · iFinD盘中行情+腾讯K线+同花顺指数（14:38盘中）',
    disclaimer: '※ 仅为AI根据盘中行情分析生成，不构成任何投资操作建议，仅供参考',
    date: '2026-08-31 14:38',
    market: '上证 3978.06 (0.65%) | 科技再涨黄金跌',
  },
  generated_at: '2026-08-31T14:38:00+08:00',
  automatic_orders: false,
  counts: { 可加仓: 0, 可入场: 4, 可试探: 4, 观望: 0, 减仓: 8 },
  rows: [],  // 由 SNAPSHOT_ROWS 填充
  disclaimers: [
    '本看板为研究视图，不构成投资建议，不生成自动订单。',
    'TD 九转为确定性指标；明日预测为形态匹配（horizon=1）且未完成 walk-forward 校准，仅供研究参考。',
    '缠论指标基于 chanlun 框架计算，仅作研究视图。',
  ],
};

// 静态行快照（结构对齐后端 _row 输出）
const SNAPSHOT_ROWS = [
  { name:'AI应用', code:'886108 · 创业板软件ETF联接（含77%） · 10jqka补拉', pct:'+2.02%', vs:'→', vol:'放量 1.24', volCls:'vu', maLabel:'多头排列', maColor:'#2ecc71', maDirs:[['M5','↑'],['M10','↑'],['M20','↑'],['M30','↑']], maVals:'M5=828 M20=843', macdLabel:'将叉', macdCls:'ti', macdVals:'DIF=4.29 DEA=6.56', kdjLabel:'J=59.4', kdjCls:'tm', kdjSub:'健康', kdjDesc:'趋势健康 · 可持有', kdVals:'K=45.1 D=37.9', tdNum:'3', tdCls:'', tdSub:'', tdDesc:'', rsiVal:'58.3', rsiDesc:'正常偏强 · 趋势中段', sectorUp:'390涨', sectorDown:'142跌', sectorRatio:'跌比27%', week:'10日 -5.3%', forecast:'-0.36%', conf:'conf 36', action:'可入场', actionColor:'#4ADE80' },
  { name:'商业航天', code:'886078 · 卫星ETF联接（含90%） · 10jqka补拉', pct:'+1.48%', vs:'↑', vol:'平量 0.95', volCls:'vu', maLabel:'多头排列', maColor:'#2ecc71', maDirs:[['M5','↑'],['M10','↑'],['M20','↑'],['M30','↑']], maVals:'M5=2081 M20=2101', macdLabel:'修复延续', macdCls:'tx', macdVals:'DIF=-5.92 DEA=-10.6', kdjLabel:'J=50.2', kdjCls:'tm', kdjSub:'健康', kdjDesc:'趋势健康 · 可持有', kdVals:'K=43.9 D=40.8', tdNum:'3', tdCls:'', tdSub:'', tdDesc:'', rsiVal:'54.4', rsiDesc:'正常偏强 · 趋势中段', sectorUp:'363涨', sectorDown:'131跌', sectorRatio:'跌比27%', week:'10日 -4.0%', forecast:'-0.74%', conf:'conf 55', action:'可入场', actionColor:'#4ADE80' },
  { name:'科创芯片ETF嘉实', code:'588200 · 嘉实上证科创板芯片ETF联接', pct:'+1.62%', vs:'↑', vol:'缩量 0.82', volCls:'vd', maLabel:'多空交织', maColor:'#f39c12', maDirs:[['M5','↑'],['M10','↑'],['M20','↑'],['M30','↓']], maVals:'M5=1.16 M20=1.18', macdLabel:'弱势金叉', macdCls:'tw', macdVals:'DIF=-0.025 DEA=-0.028', kdjLabel:'J=42.1', kdjCls:'tm', kdjSub:'健康', kdjDesc:'趋势健康 · 可持有', kdVals:'K=37.8 D=35.7', tdNum:'3', tdCls:'', tdSub:'', tdDesc:'', rsiVal:'48.3', rsiDesc:'偏弱 · 动能不足', sectorUp:'—', sectorDown:'—', sectorRatio:'—', week:'+0.0%', forecast:'+0.97%', conf:'conf 33', action:'可入场', actionColor:'#4ADE80' },
  { name:'PCB概念', code:'885959 · 电子ETF联接（含18%）', pct:'+2.24%', vs:'→', vol:'缩量 0.82', volCls:'vd', maLabel:'多头排列', maColor:'#2ecc71', maDirs:[['M5','↑'],['M10','↑'],['M20','↑'],['M30','↑']], maVals:'M5=2557 M20=2532', macdLabel:'多头延续', macdCls:'tm', macdVals:'DIF=6.88 DEA=-8.74', kdjLabel:'J=54.9', kdjCls:'tm', kdjSub:'健康', kdjDesc:'趋势健康 · 可持有', kdVals:'K=47.9 D=44.4', tdNum:'3', tdCls:'', tdSub:'', tdDesc:'', rsiVal:'55.0', rsiDesc:'正常偏强 · 趋势中段', sectorUp:'186涨', sectorDown:'49跌', sectorRatio:'跌比21%', week:'10日 -1.4%', forecast:'-0.98%', conf:'conf 32', action:'可入场', actionColor:'#4ADE80' },
  { name:'光纤概念', code:'886084 · TMT50ETF联接（含25%）', pct:'+1.29%', vs:'↓', vol:'缩量 0.83', volCls:'vd', maLabel:'多头排列', maColor:'#2ecc71', maDirs:[['M5','↑'],['M10','↑'],['M20','↑'],['M30','↑']], maVals:'M5=3667 M20=3569', macdLabel:'将死叉', macdCls:'td', macdVals:'DIF=40.1 DEA=9.74', kdjLabel:'J=69.2', kdjCls:'tm', kdjSub:'健康', kdjDesc:'趋势健康 · 可持有', kdVals:'K=60.1 D=55.5', tdNum:'3', tdCls:'', tdSub:'', tdDesc:'', rsiVal:'57.8', rsiDesc:'正常偏强 · 趋势中段', sectorUp:'74涨', sectorDown:'36跌', sectorRatio:'跌比33%', week:'10日 -1.9%', forecast:'+0.53%', conf:'conf 30', action:'可试探', actionColor:'#FBBF24' },
  { name:'稀土ETF嘉实', code:'516150 · 嘉实中证稀土产业ETF联接C', pct:'+0.06%', vs:'→', vol:'放量 1.16', volCls:'vu', maLabel:'多空交织', maColor:'#f39c12', maDirs:[['M5','↑'],['M10','↓'],['M20','↓'],['M30','↑']], maVals:'M5=1.74 M20=1.76', macdLabel:'弱势金叉', macdCls:'tw', macdVals:'DIF=-0.005 DEA=-0.005', kdjLabel:'J=47.2', kdjCls:'tm', kdjSub:'健康', kdjDesc:'趋势健康 · 可持有', kdVals:'K=40.6 D=37.2', tdNum:'3', tdCls:'', tdSub:'', tdDesc:'', rsiVal:'49.3', rsiDesc:'偏弱 · 动能不足', sectorUp:'—', sectorDown:'—', sectorRatio:'—', week:'+0.5%', forecast:'-1.73%', conf:'conf 16', action:'可试探', actionColor:'#FBBF24' },
  { name:'CPO', code:'886033 · 创业板人工智能ETF联接（含48%）', pct:'+2.12%', vs:'→', vol:'缩量 0.66', volCls:'vd', maLabel:'多头排列', maColor:'#2ecc71', maDirs:[['M5','↑'],['M10','↑'],['M20','↑'],['M30','↑']], maVals:'M5=5739 M20=5623', macdLabel:'将死叉', macdCls:'td', macdVals:'DIF=38.6 DEA=-5.20', kdjLabel:'J=52.8', kdjCls:'tm', kdjSub:'健康', kdjDesc:'趋势健康 · 可持有', kdVals:'K=49.2 D=47.5', tdNum:'3', tdCls:'', tdSub:'', tdDesc:'', rsiVal:'53.9', rsiDesc:'正常偏强 · 趋势中段', sectorUp:'168涨', sectorDown:'41跌', sectorRatio:'跌比20%', week:'10日 -3.9%', forecast:'-0.92%', conf:'conf 41', action:'可试探', actionColor:'#FBBF24' },
  { name:'锂', code:'884286 · 锂电池ETF联接 · 盘中价10jqka推算', pct:'-1.04%', vs:'↑', vol:'—', volCls:'vf', maLabel:'多头排列', maColor:'#2ecc71', maDirs:[['M5','↑'],['M10','↑'],['M20','↑'],['M30','↑']], maVals:'M5=22927 M20=22127', macdLabel:'将死叉', macdCls:'td', macdVals:'DIF=327 DEA=133', kdjLabel:'J=55.9', kdjCls:'tm', kdjSub:'健康', kdjDesc:'趋势健康 · 可持有', kdVals:'K=54.2 D=53.3', tdNum:'1', tdCls:'', tdSub:'', tdDesc:'', rsiVal:'57.7', rsiDesc:'正常偏强 · 趋势中段', sectorUp:'1涨', sectorDown:'7跌', sectorRatio:'跌比88%', week:'10日 -0.1%', forecast:'+0.97%', conf:'conf 35', action:'可试探', actionColor:'#FBBF24' },
  { name:'机床ETF华夏', code:'159663 · 华夏中证机床ETF发起式联接', pct:'+2.12%', vs:'→', vol:'缩量 0.65', volCls:'vd', maLabel:'多头排列', maColor:'#2ecc71', maDirs:[['M5','↑'],['M10','↑'],['M20','↑'],['M30','↑']], maVals:'M5=0.985 M20=1.01', macdLabel:'将死叉', macdCls:'td', macdVals:'DIF=-0.016 DEA=-0.019', kdjLabel:'J=24.3', kdjCls:'tr', kdjSub:'死叉', kdjDesc:'空头信号 · 短线看跌', kdVals:'K=29.4 D=31.9', tdNum:'3', tdCls:'', tdSub:'', tdDesc:'', rsiVal:'48.9', rsiDesc:'偏弱 · 动能不足', sectorUp:'—', sectorDown:'—', sectorRatio:'—', week:'-1.1%', forecast:'-0.83%', conf:'conf 35', action:'减仓', actionColor:'#F87171' },
  { name:'科创半导体ETF华夏', code:'588170 · 华夏上证科创板半导体材料设备ETF联接', pct:'+0.50%', vs:'→', vol:'缩量 0.7', volCls:'vd', maLabel:'多空交织', maColor:'#f39c12', maDirs:[['M5','↑'],['M10','↓'],['M20','↑'],['M30','↑']], maVals:'M5=1.00 M20=1.00', macdLabel:'将死叉', macdCls:'td', macdVals:'DIF=-0.005 DEA=-0.006', kdjLabel:'J=33.1', kdjCls:'tr', kdjSub:'死叉', kdjDesc:'空头信号 · 短线看跌', kdVals:'K=36.6 D=38.4', tdNum:'1', tdCls:'', tdSub:'', tdDesc:'', rsiVal:'49.3', rsiDesc:'偏弱 · 动能不足', sectorUp:'—', sectorDown:'—', sectorRatio:'—', week:'-1.2%', forecast:'+2.08%', conf:'conf 34', action:'减仓', actionColor:'#F87171' },
  { name:'创业板ETF富国', code:'159971 · 富国创业板ETF联接C', pct:'+0.08%', vs:'→', vol:'缩量 0.57', volCls:'vd', maLabel:'多空交织', maColor:'#f39c12', maDirs:[['M5','↑'],['M10','↓'],['M20','↓'],['M30','↓']], maVals:'M5=1.20 M20=1.23', macdLabel:'死叉', macdCls:'tr', macdVals:'DIF=-0.019 DEA=-0.018', kdjLabel:'J=11.2', kdjCls:'tb', kdjSub:'低位', kdjDesc:'超卖 · 反弹概率升高', kdVals:'K=22.6 D=28.4', tdNum:'1', tdCls:'', tdSub:'', tdDesc:'', rsiVal:'43.6', rsiDesc:'偏弱 · 动能不足', sectorUp:'—', sectorDown:'—', sectorRatio:'—', week:'-3.4%', forecast:'+0.18%', conf:'conf 31', action:'减仓', actionColor:'#F87171' },
  { name:'电网设备ETF华夏', code:'159326 · 华夏中证电网设备主题ETF联接', pct:'-0.54%', vs:'↓', vol:'缩量 0.71', volCls:'vd', maLabel:'多空交织', maColor:'#f39c12', maDirs:[['M5','↓'],['M10','↓'],['M20','↓'],['M30','↑']], maVals:'M5=1.68 M20=1.69', macdLabel:'将死叉', macdCls:'td', macdVals:'DIF=-0.013 DEA=-0.019', kdjLabel:'J=35.1', kdjCls:'tr', kdjSub:'死叉', kdjDesc:'空头信号 · 短线看跌', kdVals:'K=37.4 D=38.5', tdNum:'1↓', tdCls:'', tdSub:'', tdDesc:'', rsiVal:'46.0', rsiDesc:'偏弱 · 动能不足', sectorUp:'—', sectorDown:'—', sectorRatio:'—', week:'-0.5%', forecast:'-1.36%', conf:'conf 44', action:'减仓', actionColor:'#F87171' },
  { name:'有色金属ETF华夏', code:'516650 · 华夏有色金属ETF联接C', pct:'-1.60%', vs:'↓', vol:'缩量 0.9', volCls:'vd', maLabel:'多空交织', maColor:'#f39c12', maDirs:[['M5','↓'],['M10','↑'],['M20','↑'],['M30','↑']], maVals:'M5=1.90 M20=1.87', macdLabel:'多头延续', macdCls:'tm', macdVals:'DIF=0.034 DEA=0.030', kdjLabel:'J=100.6', kdjCls:'tr', kdjSub:'超买', kdjDesc:'短期过热 · 回调风险高', kdVals:'K=74.9 D=62.0', tdNum:'TD9', tdCls:'td9', tdSub:'下跌变盘', tdDesc:'上涨衰竭', rsiVal:'55.1', rsiDesc:'正常偏强 · 趋势中段', sectorUp:'—', sectorDown:'—', sectorRatio:'—', week:'+1.7%', forecast:'+0.19%', conf:'conf 14', action:'减仓', actionColor:'#F87171' },
  { name:'生物制品', code:'881142 · 生物医药ETF联接（含48%） · 今日价iFinD推算', pct:'-2.05%', vs:'→', vol:'—', volCls:'vf', maLabel:'多空交织', maColor:'#f39c12', maDirs:[['M5','↓'],['M10','↓'],['M20','↓'],['M30','↑']], maVals:'M5=6320 M20=6226', macdLabel:'死叉', macdCls:'tr', macdVals:'DIF=140 DEA=151', kdjLabel:'J=14.3', kdjCls:'tb', kdjSub:'低位', kdjDesc:'超卖 · 反弹概率升高', kdVals:'K=34.0 D=43.8', tdNum:'1↓', tdCls:'', tdSub:'', tdDesc:'', rsiVal:'49.1', rsiDesc:'偏弱 · 动能不足', sectorUp:'8涨', sectorDown:'47跌', sectorRatio:'跌比85%', week:'10日 -2.9%', forecast:'-1.43%', conf:'conf 29', action:'减仓', actionColor:'#F87171' },
  { name:'黄金股ETF华夏', code:'159562 · 华夏中证沪深港黄金产业股票ETF联接', pct:'-3.06%', vs:'→', vol:'缩量 0.8', volCls:'vd', maLabel:'多空交织', maColor:'#f39c12', maDirs:[['M5','↓'],['M10','↑'],['M20','↑'],['M30','↑']], maVals:'M5=2.45 M20=2.29', macdLabel:'将死叉', macdCls:'td', macdVals:'DIF=0.118 DEA=0.105', kdjLabel:'J=76.8', kdjCls:'tm', kdjSub:'健康', kdjDesc:'趋势健康 · 可持有', kdVals:'K=73.3 D=71.5', tdNum:'2', tdCls:'', tdSub:'', tdDesc:'', rsiVal:'61.0', rsiDesc:'正常偏强 · 趋势中段', sectorUp:'—', sectorDown:'—', sectorRatio:'—', week:'+1.0%', forecast:'+2.27%', conf:'conf 25', action:'减仓', actionColor:'#F87171' },
  { name:'黄金ETF国泰', code:'518800 · 国泰黄金ETF联接', pct:'-3.67%', vs:'→', vol:'平量 1.08', volCls:'vu', maLabel:'多空交织', maColor:'#f39c12', maDirs:[['M5','↓'],['M10','↓'],['M20','↑'],['M30','↑']], maVals:'M5=9.97 M20=9.51', macdLabel:'将死叉', macdCls:'td', macdVals:'DIF=0.244 DEA=0.199', kdjLabel:'J=76.4', kdjCls:'tr', kdjSub:'死叉', kdjDesc:'空头信号 · 短线看跌', kdVals:'K=81.3 D=83.8', tdNum:'2↓', tdCls:'', tdSub:'', tdDesc:'', rsiVal:'52.7', rsiDesc:'正常偏强 · 趋势中段', sectorUp:'—', sectorDown:'—', sectorRatio:'—', week:'+1.1%', forecast:'+0.45%', conf:'conf 30', action:'减仓', actionColor:'#F87171' },
];
STATIC_DATA.rows = SNAPSHOT_ROWS;

// ============ 后端数据 → 渲染格式适配 ============
// 兼容两种输入：后端 API 行（today_pct_change / td 嵌套对象）与静态快照行（pct / tdNum 平铺）
function adaptRow(row) {
  // 静态快照行：已是渲染格式，直接返回
  if (row.pct !== undefined && row.tdNum !== undefined) return row;
  const td = row.td || {};
  const forecast = row.forecast || {};
  const sector = row.sector || {};
  const sectorConcept = row.sector_concept || {};
  const breadth = row.market_breadth || null;
  const ma = row.ma || {};
  const kdj = row.kdj || {};
  const macd = row.macd || {};
  const vol = row.volume || {};
  const rsi = row.rsi || {};
  const tdLabel = td.label || '—';
  const tdIsTrigger = tdLabel.startsWith('TD');
  const week = row.week_label || '—';
  const confText = forecast.conf || (forecast.confidence != null ? `conf ${Math.round(Number(forecast.confidence))}` : '');
  // 涨跌幅防御：非有限数或 |值|>50% 视为数据异常（ETF 单日涨跌幅不可能超过 50%），显示 "—"
  const rawPct = Number(row.today_pct_change);
  const validPct = Number.isFinite(rawPct) && Math.abs(rawPct) <= 50;
  return {
    name: row.name || '—',
    code: `${row.ts_code || ''}${row.theme_l1 ? ' · ' + row.theme_l1 : ''}`,
    pct: row.today_pct_change != null && validPct ? `${rawPct >= 0 ? '+' : ''}${rawPct.toFixed(2)}%` : '—',
    vs: row.vs_yesterday || '→',
    vol: vol.text || '—',
    volCls: (vol.cls || 'dk-vf').replace('dk-', ''),
    maLabel: ma.label || '—',
    maColor: ma.color || '#f39c12',
    maDirs: ma.dirs || [],
    maVals: ma.vals || '',
    macdLabel: macd.label || '—',
    macdCls: (macd.cls || 'dk-vf').replace('dk-', ''),
    macdVals: macd.vals || '',
    kdjLabel: kdj.label || '—',
    kdjCls: (kdj.cls || 'dk-vf').replace('dk-', ''),
    kdjSub: kdj.sub || '',
    kdjDesc: kdj.desc || '',
    kdVals: kdj.vals || '',
    tdNum: tdLabel,
    tdCls: tdIsTrigger ? 'td9' : '',
    tdSub: td.sub_label || '',
    tdDesc: td.desc || '',
    rsiVal: rsi.val != null ? Number(rsi.val).toFixed(1) : '—',
    rsiDesc: rsi.desc || '',
    sectorUp: sector.up != null ? `${sector.up}涨` : '—',
    sectorDown: sector.down != null ? `${sector.down}跌` : '—',
    sectorRatio: sector.ratio != null ? `跌比${sector.ratio}%` : '—',
    sectorName: sector.sector_name || null,
    conceptUp: sectorConcept.up != null ? `${sectorConcept.up}涨` : '—',
    conceptDown: sectorConcept.down != null ? `${sectorConcept.down}跌` : '—',
    conceptRatio: sectorConcept.ratio != null ? `跌比${sectorConcept.ratio}%` : '—',
    conceptName: sectorConcept.sector_name || null,
    breathUp: breadth && breadth.up != null ? `${breadth.up}涨` : '—',
    breathDown: breadth && breadth.down != null ? `${breadth.down}跌` : '—',
    breathFlat: breadth && breadth.flat != null ? `${breadth.flat}平` : '—',
    breathTotal: breadth && breadth.total != null ? `共${breadth.total}` : '—',
    breathRatio: breadth && breadth.ratio != null ? `跌比${breadth.ratio}%` : '—',
    breathName: breadth && breadth.sector_name ? breadth.sector_name : null,
    week,
    forecast: forecast.label || (forecast.expected_return != null ? `${forecast.expected_return >= 0 ? '+' : ''}${(Number(forecast.expected_return) * 100).toFixed(2)}%` : '—'),
    conf: confText,
    action: row.action || '观望',
    actionColor: row.action === '减仓' ? '#F87171' : (row.action === '可试探' ? '#FBBF24' : (row.action === '可入场' ? '#4ADE80' : (row.action === '可加仓' ? '#4ADE80' : '#FB923C'))),
  };
}

// ============ 渲染 ============
function maCell(ma) {
  const dirs = (ma.maDirs || []).map(([k, v]) =>
    `<span style="color:${v === '↑' ? '#2ecc71' : '#e74c3c'}">${k}${v}</span>`).join(' ');
  return `<b style="color:${ma.maColor}">${esc(ma.maLabel)}</b><br>
    <span style="font-size:10px">${dirs}</span><br>
    <span style="font-size:9px; color:var(--text-dim)">${esc(ma.maVals || '')}</span>`;
}

function kdjCell(kdj) {
  const sub = kdj.kdjSub ? `<br><span class="dk-st ${kdj.kdjCls}">${esc(kdj.kdjSub)}</span>` : '';
  const desc = kdj.kdjDesc ? `<br><span style="font-size:9px; color:var(--text-dim)">${esc(kdj.kdjDesc)}</span>` : '';
  const vals = kdj.kdVals ? `<br><span style="font-size:10px; color:var(--text-dim)">${esc(kdj.kdVals)}</span>` : '';
  return `<span class="dk-st ${kdj.kdjCls}">${esc(kdj.kdjLabel)}</span>${sub}${desc}${vals}`;
}

function tdCell(row) {
  const num = row.tdNum;
  if (!num || num === '—') return '<span style="color:var(--text-dim)">—</span>';
  const cls = row.tdCls === 'td9' ? 'dk-td9' : (row.tdCls === 'td6' ? 'dk-td6' : 'dk-st dk-vf');
  const sub = row.tdSub ? `<br><span style="font-size:9px; color:${row.tdCls === 'td9' ? '#F87171' : '#FBBF24'}; font-weight:600">${esc(row.tdSub)}</span>` : '';
  const desc = row.tdDesc ? `<br><span style="font-size:9px; color:var(--text-dim)">${esc(row.tdDesc)}</span>` : '';
  return `<span class="${cls}">${esc(num)}</span>${sub}${desc}`;
}

// 板块/概念涨跌家数单元（涨/跌/跌比 + 板块名）
function breadthCell(up, down, ratio, name) {
  if (up === '—' && down === '—') return '<span style="color:var(--text-dim)">—</span>';
  return `${name ? `<div style="font-size:10px; color:var(--text-muted); margin-bottom:1px">${esc(name)}</div>` : ''}<span style="color:#2ecc71; font-size:11px">${esc(up)}</span><br><span style="color:#e74c3c; font-size:11px">${esc(down)}</span><br><span style="color:var(--text-dim); font-size:10px">${esc(ratio)}</span>`;
}

// 全市场宽度单元（涨/跌/平/总数 + 跌比），仅指数 ETF 有数据
function marketBreadthCell(r) {
  if (!r.breathName) return '<span style="color:var(--text-dim)">—</span>';
  return `<div style="font-size:10px; color:var(--text-muted); margin-bottom:1px">${esc(r.breathName)}</div>
    <span style="color:#2ecc71; font-size:11px">${esc(r.breathUp)}</span><br>
    <span style="color:#e74c3c; font-size:11px">${esc(r.breathDown)}</span><br>
    <span style="color:var(--text-dim); font-size:10px">${esc(r.breathFlat)} · ${esc(r.breathTotal)}</span><br>
    <span style="color:var(--text-dim); font-size:10px">${esc(r.breathRatio)}</span>`;
}

function renderRow(r) {
  const pctCls = String(r.pct).startsWith('-') ? 'dk-pd' : 'dk-pu';
  const vsCls = r.vs === '↑' ? 'dk-cu' : (r.vs === '↓' ? 'dk-cd' : 'dk-cs');
  const volCls = r.volCls ? `dk-vt dk-${r.volCls}` : 'dk-vt dk-vf';
  const weekColor = String(r.week).includes('-') ? '#2ecc71' : '#e74c3c';
  const fcastCls = String(r.forecast).startsWith('-') ? 'dk-pd' : 'dk-pu';
  const industryCell = breadthCell(r.sectorUp, r.sectorDown, r.sectorRatio, r.sectorName);
  const conceptCell = breadthCell(r.conceptUp, r.conceptDown, r.conceptRatio, r.conceptName);
  const marketCell = marketBreadthCell(r);
  return `<tr>
    <td><div class="dk-nc">${esc(r.name)}</div><div class="dk-cc">${esc(r.code)}</div></td>
    <td class="${pctCls}" style="font-weight:600">${esc(r.pct)}</td>
    <td style="text-align:center"><span class="dk-cb ${vsCls}">${esc(r.vs)}</span></td>
    <td><span class="${volCls}">${esc(r.vol)}</span></td>
    <td>${maCell(r)}</td>
    <td><span class="dk-st ${r.macdCls}">${esc(r.macdLabel)}</span><br><span style="font-size:10px; color:var(--text-dim)">${esc(r.macdVals)}</span></td>
    <td>${kdjCell(r)}</td>
    <td style="text-align:center">${tdCell(r)}</td>
    <td style="text-align:center"><span style="color:var(--text); font-weight:600; font-family:var(--font-mono)">${esc(r.rsiVal)}</span><br><span style="font-size:9px; color:var(--text-muted)">${esc(r.rsiDesc)}</span></td>
    <td>${industryCell}</td>
    <td>${conceptCell}</td>
    <td>${marketCell}</td>
    <td style="text-align:center"><span style="color:${weekColor}; font-family:var(--font-mono)">${esc(r.week)}</span></td>
    <td style="text-align:center"><span class="${fcastCls}" style="font-weight:600">${esc(r.forecast)}</span><br><span style="font-size:10px; color:var(--text-dim)">${esc(r.conf)}</span></td>
    <td class="dk-ac" style="color:${r.actionColor}">${esc(r.action)}</td>
  </tr>`;
}

const GROUP_RULES = {
  '可加仓': 'J<90 · 上涨放量 · MA多头排列',
  '可入场': 'J<90 · KDJ有余量 · 结构向好',
  '可试探': 'J<90 · 信号偏弱 · 结构尚可',
  '观望': '超买/偏高 · 放量滞涨 · 回调风险',
  '减仓': 'KDJ死叉 · MACD将死叉 · 多重看空共振',
};
const GROUP_COLORS = {
  '可加仓': { bg: '#1A3A2A', fg: '#4ADE80' },
  '可入场': { bg: '#1E2A40', fg: '#60A5FA' },
  '可试探': { bg: '#3A3220', fg: '#FBBF24' },
  '观望': { bg: '#3A2A20', fg: '#FB923C' },
  '减仓': { bg: '#3A2020', fg: '#F87171' },
};
const GROUP_ORDER = ['可加仓', '可入场', '可试探', '观望', '减仓'];

function renderGroup(action, rows) {
  const color = GROUP_COLORS[action] || GROUP_COLORS['观望'];
  const rule = GROUP_RULES[action] || '';
  const body = rows.length
    ? rows.map(renderRow).join('')
    : `<tr><td colspan="15" style="text-align:center; color:var(--text-dim); padding:12px">今日无「${esc(action)}」标的</td></tr>`;
  return `<div class="dk-gh">
      <span class="dk-gb" style="background:${color.bg}; color:${color.fg}">${esc(action)}</span>
      <span class="dk-gt">${esc(rule)}</span>
      <span class="dk-gd">${rows.length}个标的</span>
    </div>
    <table class="dk-tbl">
      <thead><tr>
        <th>标的</th><th>今日涨幅</th><th>较昨日</th><th>量能</th><th>均线多空</th><th>MACD</th><th>KDJ</th><th>九转</th><th>RSI</th><th>行业板块</th><th>概念板块</th><th>全市场宽度</th><th>近1周</th><th>明日预测</th><th>操作建议</th>
      </tr></thead>
      <tbody>${body}</tbody>
    </table>`;
}

function legendHtml() {
  return `
  <div class="macd-legend">
    <div class="macd-legend-title"><span class="dot"></span>图例说明：RSI · KDJ · 九转变盘 · 置信 · MACD</div>
    <div class="macd-legend-grid">
      <div class="macd-legend-item"><span class="dk-st dk-tr label">RSI≥70</span><span class="desc">超买 · 短期回调风险高</span></div>
      <div class="macd-legend-item"><span class="dk-st label" style="background:#152D3A; color:#38BDF8">50~70</span><span class="desc">正常偏强 · 趋势中段</span></div>
      <div class="macd-legend-item"><span class="dk-st dk-tw label">30~50</span><span class="desc">偏弱 · 动能不足</span></div>
      <div class="macd-legend-item"><span class="dk-st dk-tb label">RSI&lt;30</span><span class="desc">超卖 · 反弹概率升高</span></div>
    </div>
    <div style="height:8px"></div>
    <div class="macd-legend-grid" style="grid-template-columns:repeat(5, 1fr)">
      <div class="macd-legend-item"><span class="dk-st dk-tr label">超买</span><span class="desc">J&gt;100 · 短期过热 · 回调风险高</span></div>
      <div class="macd-legend-item"><span class="dk-st dk-tx label">偏高</span><span class="desc">J 90~100 · 动能偏强 · 谨慎追高</span></div>
      <div class="macd-legend-item"><span class="dk-st dk-tm label">健康</span><span class="desc">J 20~90 K≥D · 趋势健康 · 可持有</span></div>
      <div class="macd-legend-item"><span class="dk-st dk-tr label">死叉</span><span class="desc">K下穿D · 空头信号 · 短线看跌</span></div>
      <div class="macd-legend-item"><span class="dk-st dk-tb label">低位</span><span class="desc">J&lt;20 · 超卖 · 反弹概率升高</span></div>
    </div>
    <div style="height:8px"></div>
    <div class="macd-legend-grid">
      <div class="macd-legend-item"><span class="dk-st dk-tr label">TD≥9 下跌变盘</span><span class="desc">连续上涨衰竭 · 见顶信号 · 可能转跌</span></div>
      <div class="macd-legend-item"><span class="dk-st dk-tb label">TD≥9 上涨变盘</span><span class="desc">连续下跌衰竭 · 见底信号 · 可能反弹</span></div>
      <div class="macd-legend-item"><span class="dk-st dk-vf label">均线 ↑↓</span><span class="desc">↑=价格在均线上方(多) ↓=下方(空)</span></div>
      <div class="macd-legend-item"><span class="dk-st dk-tw label">量能标注</span><span class="desc">放量≥1.15 · 平量0.9~1.15 · 缩量&lt;0.9</span></div>
    </div>
    <div style="height:8px"></div>
    <div class="macd-legend-grid">
      <div class="macd-legend-item"><span class="dk-st dk-tb label">conf≥60</span><span class="desc">历史样本多 · 方向一致 · 可参考</span></div>
      <div class="macd-legend-item"><span class="dk-st dk-tw label">40~60</span><span class="desc">方向有倾向 · 样本不足 · 弱信号</span></div>
      <div class="macd-legend-item"><span class="dk-st dk-vf label">conf&lt;40</span><span class="desc">涨跌各半 · 基本等于抛硬币 · 忽略</span></div>
    </div>
    <div style="height:8px"></div>
    <div class="macd-legend-grid">
      <div class="macd-legend-item"><span class="dk-st dk-tb label">强势金叉</span><span class="desc">DIF&gt;0 · 近3日金叉 · 零轴上方多头确立</span></div>
      <div class="macd-legend-item"><span class="dk-st dk-tm label">多头延续</span><span class="desc">DIF&gt;0 · 金叉&gt;3日 · 趋势延续中</span></div>
      <div class="macd-legend-item"><span class="dk-st dk-tw label">弱势金叉</span><span class="desc">DIF&lt;0 · 近3日金叉 · 零轴下方初步企稳</span></div>
      <div class="macd-legend-item"><span class="dk-st dk-tx label">修复延续</span><span class="desc">DIF&lt;0 · 金叉&gt;3日 · 低位修复中</span></div>
      <div class="macd-legend-item"><span class="dk-st dk-ti label">将叉</span><span class="desc">DIF↗DEA · 即将金叉 · 信号待确认</span></div>
      <div class="macd-legend-item"><span class="dk-st dk-td label">将死叉</span><span class="desc">DIF↘DEA · 即将死叉 · 警惕转弱</span></div>
      <div class="macd-legend-item"><span class="dk-st dk-tr label">死叉</span><span class="desc">DIF&lt;DEA · 已死叉 · 空头信号</span></div>
      <div class="macd-legend-item"><span class="dk-st dk-vf label">均线 ↑↓</span><span class="desc">↑价格在均线上方 · ↓价格在均线下方</span></div>
    </div>
  </div>`;
}

function render(data) {
  const meta = data.meta || {
    title: 'K线企稳分析看板',
    subtitle: '',
    disclaimer: '',
    date: data.generated_at || '',
    market: '',
  };
  const rows = (data.rows || []).map(adaptRow);

  // 摘要卡片
  const summaryCards = GROUP_ORDER.map(action => {
    const count = (data.counts && data.counts[action]) || rows.filter(r => r.action === action).length;
    const color = GROUP_COLORS[action] || GROUP_COLORS['观望'];
    return `<div class="sum-card ${action === '可加仓' ? 'buy' : action === '可入场' ? 'enter' : action === '可试探' ? 'test' : action === '观望' ? 'watch' : 'reduce'}">
      <div class="sum-count" style="color:${color.fg}">${count}</div>
      <div class="sum-label">${esc(action)}</div>
      <div class="sum-desc">${esc(GROUP_RULES[action] || '')}</div>
    </div>`;
  }).join('');

  // 热度 chip（按今日涨幅排序）
  const chips = rows
    .map(r => ({ name: r.name, pct: r.pct, cls: String(r.pct).startsWith('-') ? 'cool' : 'hot' }))
    .sort((a, b) => parseFloat(b.pct) - parseFloat(a.pct))
    .map(c => `<span class="chip ${c.cls}">${esc(c.name)} ${esc(c.pct)}</span>`).join('');

  // 分组表格
  const groups = GROUP_ORDER.map(action => renderGroup(action, rows.filter(r => r.action === action))).join('');

  // 洞察（后端暂无洞察字段时用免责声明生成）
  const insights = [
    {
      title: '技术信号摘要',
      color: '#e74c3c',
      items: (data.disclaimers || ['本看板为研究视图，不构成投资建议。']).slice(0, 3),
    },
    {
      title: '预测与合规说明',
      color: '#3498db',
      items: [
        '明日预测为 K 线形态匹配（horizon=1），conf 表示历史相似窗口的方向一致性。',
        '未完成 walk-forward 校准前，所有预测标记为 not_calibrated，仅供参考。',
        '缠论指标基于 chanlun 框架（分型/笔/线段/中枢），仅作研究视图，不生成操作信号。',
      ],
    },
  ].map(g => `
    <div class="insight-card">
      <h3><span style="color:${g.color}">●</span> ${esc(g.title)}</h3>
      <ul>${g.items.map(i => `<li>${i}</li>`).join('')}</ul>
    </div>`).join('');

  const disclaimers = (data.disclaimers || []).map(item => `• ${esc(item)}`).join('<br>');
  const footerNote = '数据来源：本地日线+实时快照 | 技术指标：MACD(12,26,9) KDJ(9,3,3) RSI(14) 均线(M5/M10/M20/M30) TD九转 | 明日预测=历史形态匹配(horizon=1) conf=置信度0~100 · 未校准';

  $('#app').innerHTML = `
  <div class="header">
    <div class="header-left">
      <h1>${esc(meta.title)}</h1>
      <div class="subtitle">${esc(meta.subtitle || '')}</div>
      <div class="disclaimer">${esc(meta.disclaimer || '')}</div>
    </div>
    <div class="header-right">
      <div class="date">${esc(meta.date)}</div>
      <div class="market">${esc(meta.market || '')}</div>
    </div>
  </div>

  <div class="summary-grid">${summaryCards}</div>

  <div class="dk-root" style="padding:12px 16px">
    <div class="chip-row" style="padding:0">${chips}</div>
  </div>

  ${legendHtml()}

  <div class="warning-box">
    <h3>⚠ 合规说明</h3>
    <p>${disclaimers}</p>
  </div>

  <div class="dk-root">${groups}</div>

  <div class="insights">${insights}</div>

  <div class="footer">
    <p>${esc(meta.title)} · 研究视图（自动订单永久关闭）</p>
    <p style="margin-top:4px">${footerNote}</p>
  </div>`;
}

// ============ 数据加载 ============
async function loadSummary() {
  $('#app').innerHTML = '<div style="padding:60px;text-align:center;color:var(--text-muted)"><div class="spinner" style="width:28px;height:28px;border-radius:50%;border:2px solid currentColor;border-top-color:transparent;animation:spin .8s linear infinite;margin:0 auto 12px"></div>正在计算 K 线企稳分析…</div>';
  try {
    const token = localStorage.getItem('fundDecisionToken') || '';
    const headers = new Headers();
    if (token) headers.set('Authorization', `Bearer ${token}`);
    const response = await fetch('/api/workbench/kline/summary', { headers });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    render(data);
  } catch (error) {
    // API 不可用 -> 回退到静态快照
    console.warn('kline API 不可用，回退静态快照:', error.message);
    render(STATIC_DATA);
  }
}

document.addEventListener('DOMContentLoaded', loadSummary);
