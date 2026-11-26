import { expect, type Page } from '@playwright/test'

export async function openLegacyDecisionBoard(page: Page) {
  const board = page.locator('#etf-decisions')
  await expect(board.getByRole('heading', { name: 'ETF 决策研判矩阵', exact: true })).toBeVisible()
  const open = board.getByRole('button', { name: '原版嵌入视图', exact: true })
  if (await open.isVisible()) await open.click()
  return board.frameLocator('iframe[title="原版 ETF 决策快照"]')
}
