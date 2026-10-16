import { expect, test } from '@playwright/test'

const TOKEN = 'e2e-ops-token'

test('the dashboard asks for its token and says when it is wrong', async ({ page }) => {
  await page.goto('/ops')
  await expect(page.getByRole('heading', { name: 'AI Ops' })).toBeVisible()

  await page.getByLabel('Ops token').fill('wrong')
  await page.getByRole('button', { name: 'Open dashboard' }).click()
  await expect(page.getByRole('alert')).toHaveText('That token was not accepted.')

  await page.getByLabel('Ops token').fill(TOKEN)
  await page.getByRole('button', { name: 'Open dashboard' }).click()
  await expect(page.getByRole('navigation', { name: 'AI Ops views' })).toBeVisible()
  expect(await page.evaluate(() => sessionStorage.getItem('csa-ops-token'))).toBe(TOKEN)
})

test('a token the server stops accepting brings the form back', async ({ page }) => {
  await page.addInitScript(() => sessionStorage.setItem('csa-ops-token', 'rotated-away'))
  await page.goto('/ops')

  await expect(page.getByRole('alert')).toHaveText('That token was not accepted.')
  await expect(page.getByLabel('Ops token')).toBeVisible()
})

test('the portal itself is unchanged', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'AI Ops' })).toHaveCount(0)
})
