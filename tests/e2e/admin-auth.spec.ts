import { expect, test } from '@playwright/test'
import { ensureAdmin } from './auth.setup'

test('anonymous navigation hides protected modules and protected URL redirects', async ({ page }) => {
  await page.goto('/guide')
  await expect(page.getByRole('link', { name: '构建' })).toHaveCount(0)
  await expect(page.getByRole('link', { name: '审核' })).toHaveCount(0)
  await expect(page.getByRole('link', { name: '管理员', exact: true })).toHaveCount(0)
  await page.goto('/build')
  await expect(page).toHaveURL(/\/login\?returnTo=/)
})

test('administrator sees protected navigation and account management', async ({ page }) => {
  await ensureAdmin(page)
  await page.goto('/admin')
  await expect(page.getByRole('heading', { name: '管理员与安全审计' })).toBeVisible()
  await expect(page.getByRole('link', { name: '构建' })).toBeVisible()
  await expect(page.getByRole('link', { name: '审核' })).toBeVisible()
})
