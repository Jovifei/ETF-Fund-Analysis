import { test, expect, type Page } from '@playwright/test'
import fixture from '../tests/fixtures/chan_chart_projection.json' with { type: 'json' }
import revision from '../tests/fixtures/chan_revision_evidence.json' with { type: 'json' }
import type { ChanRevisionEvidence, ChanTransition } from '../src/lib/types'

async function syntheticObservation(page: Page, legacy = false, longIdentities = false) {
  await page.route('**/api/workspace/instruments/510300.SH/chart?**', async route => {
    const response = await route.fetch(), payload = await response.json()
    const interval = new URL(route.request().url()).searchParams.get('interval') ?? '1d'
    const metadata: ChanRevisionEvidence & { transitions: ChanTransition[] } = structuredClone(revision)
    if (longIdentities) {
      metadata.input_revision_id = 'input-'.padEnd(256, 'a')
      metadata.input_hash = 'b'.repeat(64)
      metadata.transitions = metadata.transitions.map((row, index) => ({ ...row,
        structure_key: String(index).padStart(64, 'c'),
        revision_id: row.revision_id === null ? null : 'd'.repeat(64),
        prior_revision_id: row.prior_revision_id === null ? null : 'e'.repeat(64),
      }))
    }
    await route.fulfill({ response, json: { ...payload, ...fixture.chart, ts_code: '510300.SH', interval,
      chan_observation: { ...fixture.chart.chan_observation, observation_id: `obs-${interval}`, revision_evidence: legacy ? undefined : metadata },
      research_bars: undefined, raw_overlay_allowed: true, basis_transition: false,
      sr_overlay_allowed: false, cost_overlay_allowed: false, studies: {},
      price_structures: { boxes: [], qualified: false, actionable: false },
    } })
  })
}

test('saved Chan evidence opens by keyboard and resets with the observation period', async ({ page }, info) => {
  await syntheticObservation(page)
  await page.goto('/etf/510300.SH')
  await page.getByRole('checkbox', { name: '缠论笔段中枢', exact: true }).check()
  const card = page.getByTestId('chan-evidence-card'), summary = card.locator('summary')
  await expect(card).not.toHaveAttribute('open', '')
  await summary.focus()
  await page.keyboard.press('Enter')
  await expect(card).toHaveAttribute('open', '')
  await expect(summary).toBeFocused()
  for (const label of ['本次新增观察', '本次观察有变化', '与上次观察一致', '本次未观察到', '再次观察到']) await expect(card).toContainText(label)
  await expect(card).toContainText('引擎确认未知')
  await expect(card).toContainText('2026-09-08 07:00:00 UTC')
  await expect(card.locator('[role="alert"], [aria-live]')).toHaveCount(0)
  await page.keyboard.press('Tab')
  await expect(page.getByTestId('chan-evidence-more')).toBeFocused()
  await page.keyboard.press('Enter')
  await expect(page.getByTestId('chan-transition')).toHaveCount(6)
  await expect(card).toContainText('变化状态未知')
  await card.screenshot({ path: info.outputPath('chan-evidence-desktop-open.png') })
  await page.getByRole('button', { name: '周 K', exact: true }).click()
  await expect(page.getByRole('button', { name: '周 K', exact: true })).toHaveAttribute('aria-pressed', 'true')
  await page.getByRole('checkbox', { name: '缠论笔段中枢', exact: true }).check()
  await expect(card).toContainText('obs-1w')
  await expect(card).not.toHaveAttribute('open', '')
  await expect(page.getByTestId('chan-transition')).toHaveCount(5)
})

test('saved Chan evidence wraps long identities on a 320px screen and hides with its layer', async ({ page }, info) => {
  await page.setViewportSize({ width: 320, height: 720 })
  await syntheticObservation(page, false, true)
  await page.goto('/etf/510300.SH')
  const toggle = page.getByRole('checkbox', { name: '缠论笔段中枢', exact: true })
  await toggle.check()
  const card = page.getByTestId('chan-evidence-card')
  await card.locator('summary').click()
  await expect(card).toHaveAttribute('open', '')
  await expect(card).toContainText('r4c-observed-revision-v1')
  const bounds = await card.evaluate(element => ({ scroll: element.scrollWidth, client: element.clientWidth, right: element.getBoundingClientRect().right, width: window.innerWidth }))
  expect(bounds.scroll).toBeLessThanOrEqual(bounds.client + 1)
  expect(bounds.right).toBeLessThanOrEqual(bounds.width)
  expect((await card.locator('summary').boundingBox())!.height).toBeGreaterThanOrEqual(44)
  await card.screenshot({ path: info.outputPath('chan-evidence-320px-open.png') })
  await toggle.uncheck()
  await expect(card).toHaveCount(0)
})

test('old saved observation responses expose missing evidence without inventing revisions', async ({ page }, info) => {
  await syntheticObservation(page, true)
  await page.goto('/etf/510300.SH')
  await page.getByRole('checkbox', { name: '缠论笔段中枢', exact: true }).check()
  const card = page.getByTestId('chan-evidence-card')
  await card.locator('summary').click()
  await expect(card).toContainText('当前响应未提供修订变化记录')
  await expect(card).not.toContainText('没有修订变化条目')
  await expect(page.getByTestId('chan-transition')).toHaveCount(0)
  await card.screenshot({ path: info.outputPath('chan-evidence-legacy-unknown.png') })
})
