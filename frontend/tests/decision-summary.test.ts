import { describe, expect, it } from 'vitest'
import { decisionRows, historicalClose, explainStatus } from '../src/lib/decisionSummary'

describe('responsive read projection, never a strategy', () => {
  it('keeps canonical grades and filters the same server rows', () => {
    const row={ts_code:'512480.SH',name:'半导体',grade:'数据异常',grade_reason:'缺量额',sector:{label:'芯片'}}
    expect(decisionRows({rows:[row]},'512480')).toEqual([row])
    expect(decisionRows({rows:[row]},'芯片')).toEqual([row])
    expect(decisionRows({rows:[row]},'not present')).toEqual([])
  })
  it('does not coerce missing prices or use forecast or provisional candles', () => {
    expect(historicalClose({history:[{close:null,date:'2026-09-14'}]}).price).toBeNull()
    expect(historicalClose({history:[{close:1.2,date:'2026-09-14'},{close:9,is_forecast:true},{close:8,is_provisional:true}]})).toEqual({price:1.2,date:'2026-09-14'})
    expect(historicalClose({history:[{close:'1.2'}]}).price).toBeNull()
  })
  it('retains exact reasons as text and exposes machine status', () => {
    const row={data_status:'historical_price_only',grade_reason:'<img src=x>缺量额'}
    expect(explainStatus(row)).toContain('historical_price_only')
    expect(explainStatus(row)).toContain('<img src=x>缺量额')
    expect(explainStatus({})).toContain('待核验')
  })
  it('rejects malformed row containers and identities', () => {
    expect(decisionRows({rows:{length:2}},'')).toEqual([])
    expect(decisionRows({rows:[null,{ts_code:'bad'},[]]},'')).toEqual([])
  })
})
