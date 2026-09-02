'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const test=require('node:test');
const vm=require('node:vm');
const source=fs.readFileSync(path.join(__dirname,'decision_board_workbuddy.js'),'utf8');
function load(){
  const node=()=>({classList:{add(){},remove(){},toggle(){}},addEventListener(){},getBoundingClientRect(){return{width:900}},getContext(){return{}},textContent:'',value:'',innerHTML:''});
  const context={console,Headers,URL,FormData,AbortController,clearInterval,clearTimeout,setInterval:()=>0,setTimeout:()=>0,requestAnimationFrame:()=>{},document:{cookie:'',addEventListener(){},querySelector(){return node()},querySelectorAll(){return[]}},window:{devicePixelRatio:1,location:{origin:'http://test'}},fetch:async()=>({ok:true,status:200,headers:{get:()=> 'application/json'},json:async()=>({rows:[]})})};
  context.globalThis=context;vm.runInNewContext(source,context,{filename:'decision_board_workbuddy.js'});return context.WorkBuddyDecisionBoard;
}
test('KDJ follows reference thresholds exactly',()=>{const ui=load();assert.match(ui.kdjInterpret({j:89,k:60,d:50}).note,/J 20~90/);assert.match(ui.kdjInterpret({j:90,k:60,d:50}).note,/J 90~100/);assert.match(ui.kdjInterpret({j:101,k:70,d:60}).note,/J>100/);assert.match(ui.kdjInterpret({j:19,k:20,d:10}).note,/J<20/);});
test('KDJ death cross has priority over J range',()=>{const ui=load();const item=ui.kdjInterpret({j:50,k:40,d:55,kind:'death',death:true});assert.ok(item.score<=20);assert.match(item.note,/K下穿D/);});
test('score uses six documented components and stays bounded',()=>{const ui=load();const row={ma:{kind:'bull'},macd:{kind:'gold'},kdj:{j:60,k:60,d:50,kind:'healthy'},rsi:{value:60},td:{kind:'buy',label:'TD7'},volume:{kind:'expand',ratio:1.2},returns:{today:.01},chan:{status:'inside'},forecast:{expected_return:.02,p_up:.62,calibration_status:'not_calibrated'},quote:{timestamp_verified:true,is_realtime:true},freshness:'fresh',data_status:'ok'};const s=ui.scoreRow(row,1);assert.deepEqual(Object.keys(s.components),['trend','momentum','volume','structure','forecast','data']);assert.ok(s.total>=0&&s.total<=100);assert.ok(s.components.forecast<=75);});
test('mock and stale data are heavily discounted',()=>{const ui=load();assert.ok(ui.dataScore({freshness:'fresh',quote:{timestamp_verified:true,is_realtime:true}})>ui.dataScore({freshness:'stale',data_status:'mock_unverified',quote:{timestamp_verified:false,is_realtime:false}}));});
test('percentage contract uses decimal ratios exactly once',()=>{const ui=load();assert.equal(ui.pct(.0009),'+0.09%');assert.equal(ui.pct(-.012),'-1.20%');});
test('score color follows Chinese market red-strong green-risk convention',()=>{const ui=load();assert.equal(ui.scoreClass(90),'score-strong');assert.equal(ui.scoreClass(75),'score-good');assert.equal(ui.scoreClass(60),'score-mid');assert.equal(ui.scoreClass(45),'score-watch');assert.equal(ui.scoreClass(20),'score-risk');});
test('relative direction arrows follow company screenshot semantics',()=>{const ui=load();assert.match(ui.deltaArrow(.01),/class="delta-arrow up"/);assert.match(ui.deltaArrow(-.01),/class="delta-arrow down"/);assert.match(ui.deltaArrow(0),/→/);});
test('confidence interpretation matches reference bands',()=>{const ui=load();assert.equal(ui.confidenceBand(66),'可参考');assert.equal(ui.confidenceBand(48),'弱信号');assert.equal(ui.confidenceBand(28),'低参考');});
test('main source contains the exact thirteen company-reference columns',()=>{for(const label of ['标的','今日涨幅','较昨日','量能','均线多空','MACD','KDJ','九转','RSI','板块涨跌','近1周','操作建议'])assert.match(source,new RegExp(label));assert.match(source,/明日预测/);});
test('main table keeps score inside instrument cell instead of a separate score column',()=>{assert.match(source,/score-mini/);assert.doesNotMatch(source,/<th>综合分<\/th>/);});
