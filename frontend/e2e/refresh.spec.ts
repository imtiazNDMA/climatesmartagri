import { expect, test } from '@playwright/test'
import { openPortal } from './helpers'

test('a layer that finishes loading becomes available without reloading the page', async ({ page }) => {
  let converted = false
  await page.route('**/api/health', async (route) => {
    const health = await (await route.fetch()).json()
    health.layers['fake-empty'] = converted
    await route.fulfill({ json: health })
  })
  await page.route('**/api/catalogue', async (route) => {
    const catalogue = await (await route.fetch()).json()
    for (const layer of catalogue.layers) {
      if (layer.id === 'fake-empty' && converted) layer.status = 'ready'
    }
    await route.fulfill({ json: catalogue })
  })
  await openPortal(page)
  await page.locator('[data-map-ready="true"]').waitFor()
  await page.getByRole('button', { name: 'Empty section' }).click()
  const layer = page.getByRole('switch', { name: 'Fake empty' })
  await expect(layer).toBeDisabled()
  await page.locator('.map').evaluate((element) => element.setAttribute('data-same-map', 'yes'))

  converted = true
  await expect(layer).toBeEnabled({ timeout: 15000 })
  // The page did not start over: the panel is still open and the map was not rebuilt.
  await expect(page.getByRole('heading', { name: 'Empty section' })).toBeVisible()
  await expect(page.locator('.map')).toHaveAttribute('data-same-map', 'yes')
  await expect(page.locator('[data-map-ready="true"]')).toBeVisible()
  await layer.check()
  await expect(page.getByRole('region', { name: 'Active layers' }).getByRole('listitem')).toHaveText([/Fake empty/])
})
