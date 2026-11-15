'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const test=require('node:test');
const vm=require('node:vm');
const source=fs.readFileSync(path.join(__dirname,'decision_board_workbuddy.js'),'utf8');
function load(){
  const node=()=>({classList:{add(){},remove(){},toggle(){}},addEventListener(){},getBoundingClientRect(){return{width:900}},getContext(){return{}},textContent:'',value:'',innerHTML:''});
  const requests=[];
  const context={console,Headers,URL,FormData,AbortController,clearInterval,clearTimeout,setInterval:()=>0,setTimeout:()=>0,requestAnimationFrame:()=>{},document:{cookie:'',addEventListener(){},querySelector(){return node()},querySelectorAll(){return[]}},window:{devicePixelRatio:1,location:{origin:'http'}},fetch:async(...args)=>{requests.push(args);return {ok:true,status:200,headers:{get:()=> 'application/json'},json:async()=>({rows:[]})};}};
  context.globalThis=context;vm.runInNewContext(`${source}\nglobalThis.__comparisonHtml=comparisonHtml;globalThis.__api=api;`,context,{filename:'decision_board_workbuddy.js'});return {...context.WorkBuddyDecisionBoard,comparisonHtml:context.__comparisonHtml,api:context.__api,requests};
}
test('KDJ follows reference thresholds exactly',()=>{const ui=load();assert.match(ui.kdjInterpret({j:89,k:60,d:50}).note,/J 20~90/);assert.match(ui.kdjInterpret({j:90,k:60,d:50}).note,/J 90~100/);assert.match(ui.kdjInterpret({j:101,k:70,d:60}).note,/J>100/);assert.match(ui.kdjInterpret({j:19,k:20,d:10}).note,/J<20/);});
test('KDJ death cross has priority over J range',()=>{const ui=load();const item=ui.kdjInterpret({j:50,k:40,d:55,kind:'death',death:true});assert.ok(item.score<=20);assert.match(item.note,/K下穿D/);});
test('score uses six documented components and stays bounded',()=>{const ui=load();const row={ma:{kind:'bull'},macd:{kind:'gold'},kdj:{j:60,k:60,d:50,kind:'healthy'},rsi:{value:60},td:{kind:'buy',label:'TD7'},volume:{kind:'expand',ratio:1.2},returns:{today:.01},chan:{status:'inside'},forecast:{expected_return:.02,p_up:.62,calibration_status:'not_calibrated'},quote:{timestamp_verified:true,is_realtime:true},freshness:'fresh',data_status:'ok'};const s=ui.scoreRow(row,1);assert.deepEqual(Object.keys(s.components),['trend','momentum','volume','structure','forecast','data']);assert.ok(s.total>=0&&s.total<=100);assert.ok(s.components.forecast<=75);});
test('sub-40 confidence is ignored while confidence 40 remains a weak signal',()=>{const ui=load();const ignored={forecast:{expected_return:.08,p_up:.90,confidence:39,calibration_status:'calibrated'}};const usable={forecast:{expected_return:.08,p_up:.90,confidence:40,calibration_status:'calibrated'}};const usableUncalibrated={forecast:{expected_return:.08,p_up:.90,confidence:40,calibration_status:'not_calibrated'}};assert.equal(ui.forecastScore(ignored,1),50);assert.notEqual(ui.forecastScore(usable,1),50);assert.notEqual(ui.forecastScore(usableUncalibrated,1),50);});
test('snapshot connection state expires old data and exposes poll failures',()=>{const ui=load(),now=Date.parse('2026-09-03T06:08:00Z');assert.deepEqual({...ui.snapshotConnectionState({generated_at:'2026-09-03T06:02:00Z',freshness:'fresh'},now,false)},{label:'实时快照',cls:'ok',live:true});assert.deepEqual({...ui.snapshotConnectionState({generated_at:'2026-09-03T05:59:00Z',freshness:'fresh'},now,false)},{label:'快照已过期',cls:'warn',live:false});assert.match(ui.snapshotConnectionState({generated_at:'2026-09-03T06:02:00Z',freshness:'fresh'},now,true).label,/连接异常/);assert.equal(ui.snapshotConnectionState({generated_at:'2026-09-03T06:02:00Z',freshness:'stale'},now,false).live,false);});
test('mock and stale data are heavily discounted',()=>{const ui=load();assert.ok(ui.dataScore({freshness:'fresh',quote:{timestamp_verified:true,is_realtime:true}})>ui.dataScore({freshness:'stale',data_status:'mock_unverified',quote:{timestamp_verified:false,is_realtime:false}}));});
test('percentage contract uses decimal ratios exactly once',()=>{const ui=load();assert.equal(ui.pct(.0009),'+0.09%');assert.equal(ui.pct(-.012),'-1.20%');});
test('score color follows Chinese market red-strong green-risk convention',()=>{const ui=load();assert.equal(ui.scoreClass(90),'score-strong');assert.equal(ui.scoreClass(75),'score-good');assert.equal(ui.scoreClass(60),'score-mid');assert.equal(ui.scoreClass(45),'score-watch');assert.equal(ui.scoreClass(20),'score-risk');});
test('relative direction arrows follow company screenshot semantics',()=>{const ui=load();assert.match(ui.deltaArrow(.01),/class="delta-arrow up"/);assert.match(ui.deltaArrow(-.01),/class="delta-arrow down"/);assert.match(ui.deltaArrow(0),/→/);});
test('confidence interpretation matches reference bands',()=>{const ui=load();assert.equal(ui.confidenceBand(66),'可参考');assert.equal(ui.confidenceBand(48),'弱信号');assert.equal(ui.confidenceBand(28),'忽略');assert.equal(ui.confidenceBand(40),'弱信号');assert.equal(ui.confidenceBand(39),'忽略');});
test('main source keeps the documented decision columns without duplicate day-change column',()=>{for(const label of ['标的','今日涨幅','量能','均线多空','MACD','KDJ','九转','RSI','板块涨跌','近1周','操作建议'])assert.match(source,new RegExp(label));assert.match(source,/1:'明日',3:'3日',7:'7日',20:'一个月',60:'3个月'/);assert.match(source,/\$\{horizonLabel\(state\.horizon\)\}预测/);assert.doesNotMatch(source,/较昨日/);assert.match(source,/data-sort-daily/);});
test('main table keeps score inside instrument cell instead of a separate score column',()=>{assert.match(source,/score-mini/);assert.doesNotMatch(source,/<th>综合分<\/th>/);});

test('uncalibrated p_up is labelled as historical neighbor frequency',()=>{const ui=load();assert.equal(ui.forecastProbabilityLabel({calibration_status:'not_calibrated'}),'历史相似样本上涨占比');assert.equal(ui.forecastProbabilityLabel({calibration_status:'calibrated'}),'上涨概率');});
test('forecast score shrinks weak uncalibrated evidence toward neutral',()=>{const ui=load();const weak={forecasts:{'1':{expected_return:.03,p_up:.8,confidence:55,calibration_status:'not_calibrated'}}};const strong={forecasts:{'1':{expected_return:.03,p_up:.8,confidence:80,calibration_status:'calibrated'}}};assert.ok(Math.abs(ui.forecastScore(weak,1)-50)<Math.abs(ui.forecastScore(strong,1)-50));assert.equal(ui.forecastScore({forecasts:{'1':{expected_return:.08,p_up:.9,confidence:39,calibration_status:'not_calibrated'}}},1),50);});
test('auth exposes registration and tab switching',()=>{const ui=load();assert.equal(typeof ui.registerAccount,'function');assert.equal(typeof ui.switchAuthTab,'function');});
test('decision-board API always bypasses browser cache',async()=>{const ui=load();await ui.api('/api/decision-board');assert.equal(ui.requests[0][1].cache,'no-store');});
test('indicator comparisons omit missing placeholders and use point deltas for oscillators',()=>{const ui=load();const missing=ui.comparisonHtml({indicator_comparison:{as_of_date:'2026-09-11',values:{rsi14:{current:48}}}},'rsi14','RSI');assert.match(missing,/RSI 48\.00/);assert.doesNotMatch(missing,/前 —|变化 —/);const macd=ui.comparisonHtml({indicator_comparison:{values:{macd_dif:{current:-0.1,previous:0.1}}}},'macd_dif','DIF');assert.match(macd,/变化 -0\.2000/);assert.doesNotMatch(macd,/%/);const rsi=ui.comparisonHtml({indicator_comparison:{values:{rsi14:{current:48,previous:50}}}},'rsi14','RSI');assert.match(rsi,/变化 -2\.00/);assert.doesNotMatch(rsi,/%/);});

test('audit: lower break is not classified as an upward breakout',()=>{
  const ui=load();assert.equal(ui.structureScore({chan:{status:'lower_break'}}),28);
  assert.equal(ui.structureScore({chan:{status:'upper_break'}}),82);
  assert.equal(ui.structureScore({chan:{status:'inside'}}),66);
  assert.equal(ui.structureScore({chan:{status:'unknown_break'}}),50);
});
test('audit: missing indicators are not coerced into low numeric readings',()=>{
  const ui=load();for(const value of [null,undefined,'',false]){
    assert.match(ui.kdjInterpret({j:value,k:20,d:10}).label,/不足/);
    assert.equal(ui.rsiScore({value}),50);
  }
  assert.match(ui.kdjInterpret({j:0,k:0,d:0}).label,/低位/);
  assert.equal(ui.rsiScore({value:0}),66);
});
test('audit: cached iframe state cannot hide a failed refresh',()=>{
  const handlers={}, nodes={}; const parent={postMessage(){}};
  const node=(name)=>nodes[name]??=( {value:'',disabled:true,innerHTML:'',addEventListener(){},getBoundingClientRect(){return {height:300}}} );
  const ctx={window:{parent,location:{origin:'https://fixture'},addEventListener(k,f){handlers[k]=f}},
    document:{querySelector:node},state:{},HORIZONS:[1,3,7,20,60],renderAll(){},esc:String,
    requestAnimationFrame(){},ResizeObserver:class {observe(){} disconnect(){}}};
  vm.runInNewContext(fs.readFileSync(path.join(__dirname,'decision_board_embed.js'),'utf8'),ctx);
  const emit=(error)=>handlers.message({source:parent,origin:'https://fixture',data:{type:'etf-board:state',
    horizon:1,revision:0,filter:'',board:{rows:[]},error}});
  emit('connection_failed');assert.equal(ctx.state.connectionError,true);
  emit('');assert.equal(ctx.state.connectionError,false);
});

test('tableHead includes structure columns and colspan is 15', () => {
  assert.match(source, /<th>威科夫结构<\/th><th>道氏趋势<\/th><th>ATR 波动风险<\/th>/);
  assert.match(source, /colspan="15"/);
});

test('wyckoffHtml, dowHtml, atrHtml backward compatibility: missing structure_v1 shows em-dash and does not crash', () => {
  const ui = load();
  const emptyRow = { ts_code: '510300.SH' };
  const nullRow = { ts_code: '510300.SH', structure_v1: null };

  for (const r of [emptyRow, nullRow, {}]) {
    assert.match(ui.wyckoffHtml(r), />—<\/span>/);
    assert.match(ui.wyckoffHtml(r), /未包含结构因子|样本不足/);
    assert.match(ui.dowHtml(r), />—<\/span>/);
    assert.match(ui.atrHtml(r), />—<\/span>/);
    assert.doesNotMatch(ui.atrHtml(r), /低波/);
    assert.doesNotMatch(ui.wyckoffHtml(r), /吸筹/);
    assert.doesNotMatch(ui.dowHtml(r), /上升趋势/);
  }
});

test('wyckoffHtml and dowHtml render Chinese labels and scores correctly', () => {
  const ui = load();
  const row = {
    ts_code: '510300.SH',
    structure_v1: {
      schema_version: 'structure_v1',
      as_of: '2026-11-09',
      wyckoff_phase: 'accumulation',
      wyckoff_score: 0.45,
      wyckoff_confidence: 0.65,
      dow_phase: 'uptrend',
      dow_score: 0.7,
      dow_confidence: 0.65,
    }
  };
  const wy = ui.wyckoffHtml(row);
  assert.match(wy, /吸筹/);
  assert.match(wy, /score \+0\.45/);
  assert.match(wy, /2026-11-09/);

  const dow = ui.dowHtml(row);
  assert.match(dow, /上升趋势/);
  assert.match(dow, /score \+0\.7/);
});

test('atrHtml formats risk bucket, percentage, and atr_pct_fixed_v1 metadata', () => {
  const ui = load();
  const row = {
    ts_code: '510300.SH',
    structure_v1: {
      schema_version: 'structure_v1',
      as_of: '2026-11-09',
      atr14: 0.0456,
      atr_pct: 0.0125,
      atr_risk_bucket: 'mid',
    }
  };
  const html = ui.atrHtml(row);
  assert.match(html, /中波/);
  assert.match(html, /1\.25%/);
  assert.match(html, /ATR14: 0\.0456/);
  assert.match(html, /规则: atr_pct_fixed_v1/);
  assert.match(html, /class="atr-mid"/);
});
