import { mount } from '@vue/test-utils'
import { describe, it, expect } from 'vitest'
import AvailabilityMatrix from '../src/components/AvailabilityMatrix.vue'
describe('availability matrix', () => {
 it('shows nine controlled modules for old responses', () => { const w=mount(AvailabilityMatrix); expect(w.findAll('.availability-row')).toHaveLength(9); expect(w.text()).toContain('未提供状态') })
 it('keeps horizon differences and hides unknown reasons', () => { const w=mount(AvailabilityMatrix,{props:{availability:{forecasts:{status:'unavailable',reason_code:'feature_shortage',by_horizon:{'1':{status:'blocked',reason_code:'private-url'},'3':{status:'available',reason_code:null}}}} as any}}); expect(w.text()).toContain('1 日：已阻断'); expect(w.text()).toContain('3 日：可读'); expect(w.text()).not.toContain('private-url') })
})
