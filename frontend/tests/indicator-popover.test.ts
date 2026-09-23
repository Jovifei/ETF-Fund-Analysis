import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import EtfChart from '../src/components/EtfChart.vue'
import type { ChartData } from '../src/lib/types'
vi.mock('../src/lib/chartAdapter',()=>({
 groupsForLevel:()=>['PIVOT'],
 ChartAdapter:class {chart={resize:vi.fn()};setIndicatorSelection(){};setStudySelection(){};range(){};reset(){};destroy(){}}
}))
const data={ts_code:'TEST.SH',interval:'1d',available:true,adjust:'none',bars:[{date:'2026-09-01',open:1,high:2,low:1,close:2,volume:100,amount:null,indicators:{ma5:1}}]} as ChartData
const wrappers:ReturnType<typeof mount>[]=[]
beforeEach(()=>{Object.defineProperty(window,'innerHeight',{configurable:true,value:600});Object.defineProperty(window,'innerWidth',{configurable:true,value:390})})
afterEach(()=>{wrappers.forEach(w=>w.unmount());wrappers.length=0;vi.restoreAllMocks()})
function chart(){const w=mount(EtfChart,{props:{data},attachTo:document.body});wrappers.push(w);return w}
describe('indicator popup viewport and Escape',()=>{
 it('keeps the entire panel within the viewport when its trigger is near the bottom',async()=>{
  const w=chart();await flushPromises()
  const details=w.get('[data-testid="indicator-picker"]'),el=details.element as HTMLDetailsElement
  vi.spyOn(el,'getBoundingClientRect').mockReturnValue({x:150,y:510,left:150,right:290,top:510,bottom:554,width:140,height:44,toJSON(){}})
  Object.defineProperty(el,'offsetHeight',{configurable:true,value:44})
  el.open=true;await details.trigger('toggle');await flushPromises()
  const menu=w.get('.indicator-menu').element as HTMLElement
  expect(menu.style.maxHeight).not.toBe('')
  const top=510+parseFloat(menu.style.top),height=parseFloat(menu.style.maxHeight)
  expect(top).toBeGreaterThanOrEqual(12)
  expect(top+height).toBeLessThanOrEqual(588)
 })
 it('closes an open indicator panel before the fallback fullscreen shell',async()=>{
  const w=chart();await flushPromises();await w.get('[data-testid="chart-fullscreen"]').trigger('click');await flushPromises()
  expect(w.classes()).toContain('expanded-chart')
  const panel=w.get('[data-testid="indicator-picker"]').element as HTMLDetailsElement
  panel.open=true
  document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true,cancelable:true}));await flushPromises()
  expect(panel.open).toBe(false)
  expect(w.classes()).toContain('expanded-chart')
  document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true,cancelable:true}));await flushPromises()
  expect(w.classes()).not.toContain('expanded-chart')
 })
})

import { popupLayout } from '../src/lib/popupLayout'
describe('popup geometry at zoom and visual viewport offsets',()=>{
 for(const scale of [.8,1,1.25,2])it(`bounds both axes at scale ${scale}`,()=>{
  const anchor={left:250,right:380,top:530,bottom:570},view={left:40,top:60,width:350,height:550}
  const box=popupLayout(anchor,view,scale)!
  const left=anchor.left+box.left*scale,top=anchor.top+box.top*scale
  expect(left).toBeGreaterThanOrEqual(view.left+12)
  expect(left+box.width*scale).toBeLessThanOrEqual(view.left+view.width-12+.001)
  expect(top).toBeGreaterThanOrEqual(view.top+12-.001)
  expect(top+box.maxHeight*scale).toBeLessThanOrEqual(view.top+view.height-12+.001)
 })
 it('opens below when space is available and rejects an offscreen trigger',()=>{
  expect(popupLayout({left:100,right:200,top:50,bottom:90},{left:0,top:0,width:1440,height:1000})!.side).toBe('below')
  expect(popupLayout({left:100,right:200,top:-80,bottom:-40},{left:0,top:0,width:1440,height:1000})).toBeNull()
 })
 it('does not emit invalid dimensions for an unavailable viewport',()=>{
  expect(popupLayout({left:0,right:0,top:0,bottom:0},{left:0,top:0,width:0,height:0})).toBeNull()
 })
})
