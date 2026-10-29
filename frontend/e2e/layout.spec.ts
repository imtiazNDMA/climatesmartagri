import { expect, test } from '@playwright/test'
import { openPortal } from './helpers'

test('a long layer name does not push the layer controls out of the active layers box', async ({ page }) => {
  await page.route('**/api/catalogue', async (route) => {
    const response = await route.fetch()
    const catalogue = await response.json()
    for (const layer of catalogue.layers) {
      if (layer.id === 'fake-static') layer.title = 'A very long layer name that describes its contents at length (district)'
    }
    await route.fulfill({ json: catalogue })
  })
  await openPortal(page)
  await page.getByRole('button', { name: 'Beta section' }).click()
  await page.getByRole('switch', { name: /A very long layer name/ }).check()
  const box = (await page.getByRole('region', { name: 'Active layers' }).boundingBox())!
  const remove = (await page.getByRole('button', { name: /^Remove A very long/ }).boundingBox())!
  expect(remove.x + remove.width).toBeLessThanOrEqual(box.x + box.width)
  expect(box.x + box.width).toBeLessThanOrEqual(page.viewportSize()!.width)
})
