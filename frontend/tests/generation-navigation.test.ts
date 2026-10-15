import {expect,it} from 'vitest'
import {mount} from '@vue/test-utils'
import DecisionSummary from '../src/components/DecisionSummary.vue'

it('both narrow-screen detail links keep the displayed generation',()=>{
  const wrapper=mount(DecisionSummary,{props:{filter:'',horizon:1,board:{generation:7,rows:[{ts_code:'510300.SH',name:'test',grade:'数据异常'}]}},
    global:{stubs:{RouterLink:{props:['to'],template:'<a :href="to"><slot/></a>'}}}})
  const links=wrapper.findAll('a[href^="/etf/"]')
  expect(links).toHaveLength(2)
  for(const link of links) expect(link.attributes('href')).toBe('/etf/510300.SH?generation=7')
  wrapper.unmount()
})
