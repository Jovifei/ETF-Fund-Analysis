from __future__ import annotations

import json
import subprocess
from pathlib import Path


def test_demo_mode_transitions_and_formal_mutation_mutex() -> None:
    static = Path(__file__).parents[1] / "app" / "static" / "app.js"
    harness = r"""
const fs = require('fs');
const vm = require('vm');
const source = fs.readFileSync(process.argv[1], 'utf8');
const node = () => ({
  textContent: '', value: '', disabled: false, className: '',
  classList: {add(){}, remove(){}, toggle(){}},
  setAttribute(){}, focus(){}, getBoundingClientRect(){return {width:800,height:400}},
});
const context = {
  console, setTimeout, clearTimeout, setInterval, clearInterval, URL,
  Headers, AbortController, FormData, TextEncoder, TextDecoder,
  document: {querySelector:(selector)=>selector === '#marketSourceForm' ? null : node(), querySelectorAll:()=>[], addEventListener(){}, activeElement:node()},
  window: {devicePixelRatio:1, location:{origin:'http://test.local'}, addEventListener(){}, removeEventListener(){}},
  localStorage: {getItem(){return 'unit-token'}, setItem(){}, removeItem(){}},
  confirm:()=>true,
};
context.globalThis = context;
vm.runInNewContext(source + '\nthis.__test={state,api,enterDemoMode,exitDemoMode,beginModeTransition};', context, {filename: process.argv[1]});
const t = context.__test;
const state = t.state;
state.token = 'unit-token';
state.renderOverride = () => {};
state.settings = {quote_refresh_minutes: 3};
let calls = [];
let eventRestarts = 0;
state.eventsRestartOverride = () => { eventRestarts += 1; };
const response = payload => ({ok:true, status:200, statusText:'OK', headers:{get:()=> 'application/json'}, json:async()=>payload});
let pendingResolve;
context.fetch = (url, options={}) => {
  calls.push({url, method:options.method || 'GET'});
  if (url === '/api/holdings/lock') return new Promise(resolve => { pendingResolve = resolve; });
  if (url === '/api/holdings/fail') return Promise.reject(new Error('synthetic write failure'));
  if (url === '/api/demo/load') return Promise.resolve(response({demo:true,is_mock:true,research_only:true,actionable:false,status:'ready',status_label:'演示数据已就绪',summary:{},instruments:[],market_context:[],holdings:[],news:[],tasks:[],provider_health:[],signal_grade:{},boards:{}}));
  if (url === '/api/demo/reset') return Promise.resolve(response({demo:true,is_mock:true,research_only:true,actionable:false,status:'pending',status_label:'待初始化',summary:{},instruments:[],market_context:[],holdings:[],news:[],tasks:[],provider_health:[],signal_grade:{},boards:{}}));
  if (url === '/api/settings') return Promise.resolve(response({market_data_tier:'usable',active_provider:'akshare',quote_refresh_minutes:3,ftshare_enabled:false,ftshare_qualification:'unverified'}));
  if (url === '/api/bootstrap') return Promise.resolve(response({demo:false,summary:{instrument_count:0,live_quote_count:0,state_counts:{},market_width:{up:0,down:0,unchanged:0},provider:'akshare',app_env:'test',is_mock:false},instruments:[],market_context:[],holdings:[],news:[],tasks:[],provider_health:[]}));
  if (url === '/api/reports') return Promise.resolve(response([]));
  return Promise.resolve(response({}));
};
const tick = () => new Promise(resolve => setTimeout(resolve, 0));
(async () => {
  // A pending formal write refuses the mode switch, then permits it after settlement.
  state.demoMode = false; calls = [];
  const pending = t.api('/api/holdings/lock', {method:'PUT', body:'{}'}).catch(()=>{});
  await tick();
  if (state.formalMutationCount !== 1) throw new Error('formal mutation was not tracked');
  await t.enterDemoMode();
  if (state.demoMode || calls.some(item => item.url === '/api/demo/load')) throw new Error('entered demo during formal mutation');
  pendingResolve(response({}));
  await pending;
  if (state.formalMutationCount !== 0) throw new Error('formal mutation counter leaked');
  await t.enterDemoMode();
  if (!state.demoMode || state.modeTransition) throw new Error('successful enter did not retain DEMO');

  // A failed formal request still releases the counter.
  state.demoMode = false;
  await t.api('/api/holdings/fail', {method:'PUT', body:'{}'}).catch(()=>{});
  if (state.formalMutationCount !== 0) throw new Error('failed mutation leaked counter');
  const baseFetch = context.fetch;
  const abortController = new AbortController();
  context.fetch = (url, options={}) => {
    if (url === '/api/holdings/abort') return new Promise((resolve, reject) => options.signal.addEventListener('abort', () => reject(Object.assign(new Error('aborted'), {name:'AbortError'}))));
    return baseFetch(url, options);
  };
  const aborted = t.api('/api/holdings/abort', {method:'PUT', body:'{}', signal:abortController.signal}).catch(()=>{});
  await tick(); abortController.abort(); await aborted;
  if (state.formalMutationCount !== 0) throw new Error('aborted mutation leaked counter');
  context.fetch = baseFetch;

  // Enter failure returns to formal state and restarts formal SSE exactly once.
  state.demoMode = false; state.data = {demo:false,summary:{}}; eventRestarts = 0; calls = [];
  const oldFetch = baseFetch;
  context.fetch = (url, options={}) => url === '/api/demo/load' ? Promise.reject(new Error('synthetic failure')) : oldFetch(url, options);
  await t.enterDemoMode();
  if (state.demoMode || state.modeTransition || eventRestarts !== 1) throw new Error('enter failure did not restore formal lifecycle');
  if (state.refreshTimer) clearInterval(state.refreshTimer);

  // Exit success reloads formal data and reconnects SSE exactly once.
  context.fetch = oldFetch; state.demoMode = true; state.data = {demo:true}; eventRestarts = 0; calls = [];
  await t.exitDemoMode();
  if (state.demoMode || state.modeTransition || state.data.demo || eventRestarts !== 1) throw new Error('exit did not restore formal lifecycle ' + JSON.stringify({demo:state.demoMode, transition:state.modeTransition, data:state.data, eventRestarts, calls}));
  if (state.refreshTimer) clearInterval(state.refreshTimer);
  process.stdout.write(JSON.stringify({ok:true, formalMutationCount:state.formalMutationCount, calls:calls.map(item=>item.url), eventRestarts}));
})().catch(error => { process.stderr.write(String(error.stack || error)); process.exit(1); });
"""
    result = subprocess.run(
        ["node", "-e", harness, str(static)],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["formalMutationCount"] == 0
    assert payload["eventRestarts"] == 1
