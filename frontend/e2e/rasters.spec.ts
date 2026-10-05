import { expect, test } from '@playwright/test'
import { openPortal } from './helpers'

const TILE_URL = '/api/cog/tiles/WebMercatorQuad/{z}/{x}/{y}.png?layer=fake-static'
const PIXEL = Buffer.from(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==',
  'base64',
)

test('a raster layer with its own tile address is drawn from that address', async ({ page }) => {
  await page.route('**/api/catalogue', async (route) => {
    const catalogue = await (await route.fetch()).json()
    for (const layer of catalogue.layers) {
      if (layer.id === 'fake-static') Object.assign(layer, { tile_url: TILE_URL, max_zoom: 14 })
    }
    await route.fulfill({ json: catalogue })
  })
  const requested: string[] = []
  await page.route('**/api/cog/**', (route) => {
    requested.push(new URL(route.request().url()).pathname + new URL(route.request().url()).search)
    return route.fulfill({ status: 200, contentType: 'image/png', body: PIXEL })
  })
  await openPortal(page)
  await page.locator('[data-map-ready="true"]').waitFor()
  await page.getByRole('button', { name: 'Beta section' }).click()
  await page.getByRole('switch', { name: 'Fake static' }).check()

  await expect(page.getByRole('region', { name: 'Active layers' }).getByText('Could not load')).toHaveCount(0)
  // The cheap whole-world check, then real map tiles, all from the layer's own address.
  await expect.poll(() => requested).toContain('/api/cog/tiles/WebMercatorQuad/0/0/0.png?layer=fake-static')
  await expect
    .poll(() => requested.filter((url) => /WebMercatorQuad\/[1-9]\d?\/\d+\/\d+\.png\?layer=fake-static$/.test(url)).length)
    .toBeGreaterThan(0)
})
