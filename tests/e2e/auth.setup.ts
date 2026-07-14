import type { Page } from '@playwright/test'

export async function ensureAdmin(page: Page) {
  let response = await page.request.post('/api/auth/login', { data: { username: 'admin', password: 'Better@Pass2' } })
  if (!response.ok()) response = await page.request.post('/api/auth/login', { data: { username: 'admin', password: 'Pass@word1' } })
  if (!response.ok()) throw new Error(`Administrator login failed: ${response.status()}`)
  const session = await response.json()
  if (session.must_change_password) {
    const changed = await page.request.post('/api/auth/change-password', {
      headers: { 'X-CSRF-Token': session.csrf_token },
      data: { current_password: 'Pass@word1', new_password: 'Better@Pass2' },
    })
    if (!changed.ok()) throw new Error(`Administrator password change failed: ${changed.status()}`)
    return (await changed.json()).csrf_token as string
  }
  return session.csrf_token as string
}
