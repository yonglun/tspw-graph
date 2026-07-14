import { expect, test } from '@playwright/test'
import { ensureAdmin } from './auth.setup'

test('uploads, builds and explores an isolated graph', async ({ page }) => {
  await ensureAdmin(page)
  await page.goto('/build')
  await page.getByLabel('TXT 小说').setInputFiles('fixtures/sample-novel.txt')
  await page.getByLabel('项目标题').fill('E2E 小说')
  await page.getByLabel('模型配置').selectOption('fixed:test')
  await page.getByRole('button', { name: '开始构建' }).click()
  await expect(page.getByText('构建完成')).toBeVisible({ timeout: 30_000 })
  await expect(page.getByTestId('accepted-facts')).not.toContainText('0')
  await page.getByRole('link', { name: '进入项目图谱' }).click()
  await expect(page).toHaveURL(/\/graph\?project=project-/)
  await page.getByRole('searchbox').fill('测试人物')
  await expect(page.getByRole('button', { name: /测试人物/ }).first()).toBeVisible()
})
