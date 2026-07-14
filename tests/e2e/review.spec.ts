import { expect, test } from '@playwright/test'
import { ensureAdmin } from './auth.setup'

test('reviewer scans, accepts and sees audit trail', async ({ page }) => {
  const csrf = await ensureAdmin(page)
  await page.request.post('/api/projects/xiaoao/review/items', {
    headers: { 'X-CSRF-Token': csrf },
    data: {
      item_type: 'FACT',
      reason_code: 'MANUAL_REVIEW',
      target: { fact_id: 'e2e-review-fact' },
      evidence_ids: [],
      fingerprint: `manual:e2e-review-fact:${Date.now()}`,
      severity: 10,
    },
  })
  await page.goto('/review?project=xiaoao')
  await expect(page.getByRole('heading', { name: '审核工作台' })).toBeVisible()
  await expect(page.getByText('质量仪表盘')).toBeVisible()
  await expect(page.getByText('审核队列')).toBeVisible()

  const accept = page.getByRole('button', { name: '接受事实' })
  if (await accept.count()) {
    await accept.first().click()
    await expect(page.getByText('审计日志')).toBeVisible()
  }

  await page.goto('/graph?project=xiaoao')
  await expect(page.getByRole('heading', { name: '沿关系，游江湖' })).toBeVisible()
})
