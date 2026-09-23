import {describe,it,expect} from 'vitest'
import {studyAvailable,volumeAvailable} from '../src/lib/chartStudies'
import type {ChartData} from '../src/lib/types'
const data=(interval:string,indicators:Record<string,number|null>,volume:number|null=null)=>({interval,bars:[{date:'2026-09-01',open:1,high:2,low:1,close:2,volume,indicators}]} as ChartData)
describe('server study availability',()=>{
 it('never promotes missing, NaN or unknown indicator fields',()=>{
  expect(studyAvailable(data('1d',{ma5:null}),'MA')).toBe(false)
  expect(studyAvailable(data('1d',{ma5:NaN}),'MA')).toBe(false)
  expect(studyAvailable(data('1d',{sar:20}),'SAR')).toBe(false)
  expect(volumeAvailable(data('1d',{}))).toBe(false)
 })
 it('zero is a valid observation, not an absent value',()=>{
  expect(studyAvailable(data('1d',{macd_dif:0}),'MACD')).toBe(true)
  expect(volumeAvailable(data('1d',{},0))).toBe(true)
 })
 it('never puts daily indicators on minute series',()=>{
  expect(studyAvailable(data('30m',{ma5:12}),'MA')).toBe(false)
 })
})
