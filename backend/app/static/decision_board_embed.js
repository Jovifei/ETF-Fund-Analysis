/* Uses the original template and renderer. No fetch, authentication, polling,
   credentials, duplicate decision calculation, or independent navigation here. */
'use strict';
function sendHost(message){window.parent.postMessage(message,window.location.origin);}
function sizeHost(){sendHost({type:'etf-board:height',height:Math.ceil(document.querySelector('.report-shell').getBoundingClientRect().height)});}
window.addEventListener('message',event=>{
  if(event.source!==window.parent||event.origin!==window.location.origin)return;
  const value=event.data;
  if(value?.type!=='etf-board:state')return;
  if(!HORIZONS.includes(value.horizon))return;
  state.horizon=value.horizon;
  state.filter=typeof value.filter==='string'?value.filter.slice(0,128):'';
  document.querySelector('#horizonSelect').value=String(state.horizon);
  document.querySelector('#searchInput').value=state.filter;
  if(value.board&&Array.isArray(value.board.rows)){
    state.board=value.board;state.connectionError=false;renderAll();
  }else if(value.error){
    document.querySelector('#boardArea').innerHTML='<div class="empty">'+esc(value.error)+'</div>';
  }
  requestAnimationFrame(sizeHost);
});
document.querySelector('#horizonSelect').addEventListener('change',event=>{
  state.horizon=Number(event.target.value);
  sendHost({type:'etf-board:controls',horizon:state.horizon,filter:state.filter});
});
document.querySelector('#searchInput').addEventListener('input',event=>{
  state.filter=event.target.value.slice(0,128);if(state.board)renderAll();
  sendHost({type:'etf-board:controls',horizon:state.horizon,filter:state.filter});
});
const sizeObserver=new ResizeObserver(()=>requestAnimationFrame(sizeHost));
sizeObserver.observe(document.querySelector('.report-shell'));
window.addEventListener('pagehide',()=>sizeObserver.disconnect(),{once:true});
sendHost({type:'etf-board:ready'});
