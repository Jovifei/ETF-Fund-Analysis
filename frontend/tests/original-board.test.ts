// @vitest-environment node
import { describe, expect, it, vi } from 'vitest'
import { readFileSync } from 'node:fs'
import { runInNewContext } from 'node:vm'

const source = readFileSync(new URL('../../backend/app/static/decision_board_embed.js', import.meta.url), 'utf8')
function frame() {
  const handlers: Record<string, (e: any) => void> = {}, inputs: Record<string, any> = {}, sent: unknown[] = []
  const nodes: Record<string, any> = {}
  const parent = {postMessage: (value: unknown) => sent.push(value)}
  const state = {filter:'',horizon:1,board:null,connectionError:false}
  const window = {parent,location:{origin:'https://example.test'},addEventListener:(key:string,fn:any)=>{handlers[key]=fn}}
  const document = {querySelector:(key:string) => nodes[key] ??= {value:'',innerHTML:'',getBoundingClientRect:()=>({height:800}),addEventListener:(event:string,fn:any)=>{inputs[key+event]=fn}}}
  const renderAll = vi.fn()
  runInNewContext(source,{window,document,state,HORIZONS:[1,3,5,10],renderAll,esc:(value:string)=>value,
    requestAnimationFrame:(fn:any)=>fn(),ResizeObserver:class{observe(){} disconnect(){}}})
  const deliver=(data:any)=>handlers.message({source:parent,origin:window.location.origin,data})
  return {state,deliver,handlers,inputs,parent,renderAll,sent}
}
describe('original-template host protocol',()=>{
  it('does not erase a newer filter when an old horizon response arrives',()=>{
    const f=frame()
    f.deliver({type:'etf-board:state',revision:0,horizon:1,filter:'',board:{rows:[]}})
    f.inputs['#searchInputinput']({target:{value:'512480'}})
    f.deliver({type:'etf-board:state',revision:0,horizon:5,filter:'',board:{rows:[]}})
    expect(f.state.filter).toBe('512480')
    expect(f.sent).toContainEqual({type:'etf-board:controls',revision:1,horizon:1,filter:'512480'})
  })
  it('restores the latest host controls after a frame is reattached',()=>{
    const f=frame()
    f.deliver({type:'etf-board:state',revision:7,horizon:5,filter:'黄金',board:{rows:[]}})
    expect(f.state.horizon).toBe(5);expect(f.state.filter).toBe('黄金')
    f.inputs['#horizonSelectchange']({target:{value:'10'}})
    expect(f.sent).toContainEqual({type:'etf-board:controls',revision:8,horizon:10,filter:'黄金'})
  })
  it('ignores foreign origins and unrelated windows',()=>{
    const f=frame(), data={type:'etf-board:state',revision:99,horizon:5,filter:'invalid',board:{rows:[]}}
    f.handlers.message({origin:'https://other.test',source:f.parent,data})
    f.handlers.message({origin:'https://example.test',source:{},data})
    expect(f.state.filter).toBe('');expect(f.renderAll).not.toHaveBeenCalled()
  })
})
