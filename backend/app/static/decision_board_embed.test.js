'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const test=require('node:test');
const vm=require('node:vm');

test('cached iframe data preserves an independent failed-refresh state',()=>{
  const handlers={},nodes={},parent={postMessage(){}};
  const node=(name)=>nodes[name]??={value:'',disabled:true,innerHTML:'',addEventListener(){},getBoundingClientRect(){return {height:300}}};
  const ctx={window:{parent,location:{origin:'https://fixture'},addEventListener(k,f){handlers[k]=f}},
    document:{querySelector:node},state:{},HORIZONS:[1,3,5,10,20],renderAll(){},esc:String,
    requestAnimationFrame(){},ResizeObserver:class {observe(){} disconnect(){}}};
  vm.runInNewContext(fs.readFileSync(path.join(__dirname,'decision_board_embed.js'),'utf8'),ctx);
  const board={rows:[]};
  const emit=(error)=>handlers.message({source:parent,origin:'https://fixture',data:{
    type:'etf-board:state',horizon:1,revision:0,filter:'',board,error}});
  emit('connection_failed');assert.equal(ctx.state.connectionError,true);assert.equal(ctx.state.board,board);
  emit('');assert.equal(ctx.state.connectionError,false);
});
