import { describe, expect, it } from 'vitest'
import { router, etfPath } from '../src/router'
describe('one ETF route and bookmark compatibility', () => {
  it('does not create a separate portfolio chart URL', () => { expect(etfPath('512480.SH')).toBe('/etf/512480.SH'); expect(router.resolve('/etf/512480.SH').matched[0].path).toBe('/etf/:code') })
  it('keeps old paths as redirects rather than duplicate pages', () => { for (const path of ['/legacy', '/workbench/1430', '/workbench/kline', '/system', '/research']) expect(router.resolve(path).matched[0].redirect).toBeTruthy() })
  it('has an explicit not-found page', () => { expect(router.resolve('/not-a-page').meta.title).toBe('页面不存在') })
})
