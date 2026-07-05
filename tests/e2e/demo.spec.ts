import { expect, test } from '@playwright/test'

test('visitor learns, explores and verifies an answer', async ({ page }) => {
  await page.goto('/guide')
  await expect(page.getByRole('heading', { name: /看懂.*知识图谱/ })).toBeVisible()

  await page.getByRole('link', { name: '图谱', exact: true }).click()
  await page.getByRole('searchbox').fill('令狐冲')
  await page.getByRole('button', { name: /令狐沖/ }).click()
  await expect(page.getByText('原文证据')).toBeVisible()

  await page.getByRole('link', { name: '问答', exact: true }).click()
  await page.getByRole('button', { name: '令狐冲的师父是谁？' }).click()
  await page.getByRole('button', { name: '查询图谱' }).click()
  await expect(page.getByRole('heading', { name: /嶽不群/ })).toBeVisible()
  await page.getByRole('button', { name: /查看技术细节/ }).click()
  await expect(page.locator('pre')).toContainText('MATCH')

  await page.getByRole('link', { name: '故事线', exact: true }).click()
  await page.getByRole('combobox', { name: '人物' }).selectOption({ label: '令狐沖' })
  await expect(page.getByRole('heading', { name: '思過崖傳劍' })).toBeVisible()
})
