import { describe, expect, it } from 'vitest'
import { direction, num, pct, frequency, forecastLabel, stamp } from '../src/lib/format'
describe('display contracts', () => {
  it('does not coerce unknown values into fake zeroes', () => { expect(num(null)).toBe('—'); expect(num('12')).toBe('—'); expect(num(NaN)).toBe('—'); expect(pct(undefined)).toBe('—'); expect(num(0)).toBe('0.00') })
  it('uses explicit ratio units and Chinese market directions', () => { expect(pct(.025)).toBe('+2.50%'); expect(direction(.02)).toBe('bull'); expect(direction(-.02)).toBe('bear'); expect(direction(null)).toBe('neutral') })
  it('does not call a status string calibration proof', () => { expect(forecastLabel({ calibration_status: 'calibrated' })).toContain('历史'); expect(frequency({ p_up: .62 })).toBe('62%'); expect(frequency(undefined)).toBe('—') })
  it('renders source dates in Shanghai rather than browser zone', () => { expect(stamp('2026-09-01T06:30:00Z')).toContain('14:30'); expect(stamp(null)).toBe('尚无记录') })
})
