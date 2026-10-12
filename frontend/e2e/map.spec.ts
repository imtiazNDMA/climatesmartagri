import { expect, test } from '@playwright/test'
import { mockTiles, openPortal } from './helpers'

test('the map starts and reports ready', async ({ page }) => {
  await openPortal(page)
  await expect(page.locator('[data-map-ready="true"]')).toBeVisible()
})

test('falls back to a plain background when the background map is unreachable', async ({ page }) => {
  await mockTiles(page)
  await page.route('https://basemap.test/**', (route) => route.abort())
  await page.goto('/')
  await expect(page.getByText('Background map unavailable')).toBeVisible()
  await expect(page.locator('[data-map-ready="true"]')).toBeVisible()
})

test('still starts when boundaries are not loaded', async ({ page }) => {
  await page.route('**/api/places/boundaries**', (route) =>
    route.fulfill({ status: 404, json: { detail: { message: 'none', reason: 'no-data' } } }),
  )
  await openPortal(page)
  await expect(page.locator('[data-map-ready="true"]')).toBeVisible()
})

test('requests tiles for an active layer, with the year when the layer has years', async ({ page }) => {
  const requested: string[] = []
  page.on('request', (request) => {
    if (request.url().includes('/api/tiles/')) requested.push(request.url())
  })
  await openPortal(page)
  await page.locator('[data-map-ready="true"]').waitFor()
  await page.getByRole('button', { name: 'Alpha section' }).click()
  await page.getByRole('switch', { name: 'Fake yearly' }).check()
  await expect.poll(() => requested.some((url) => /fake-yearly\/\d+\/\d+\/\d+\?year=2010/.test(url))).toBe(true)
})

test('the map worker loads, so boundaries can be drawn', async ({ page }) => {
  const errors: string[] = []
  page.on('console', (message) => {
    if (message.type() === 'error') errors.push(message.text())
  })
  page.on('pageerror', (error) => errors.push(error.message))
  await openPortal(page)
  await page.locator('[data-map-ready="true"]').waitFor()
  // Boundaries are GeoJSON sources, which are processed in the worker.
  await expect(page.locator('[data-boundaries-drawn="true"]')).toBeVisible()
  expect(errors.filter((text) => /worker/i.test(text))).toEqual([])
})

test('a click names a district in a popup, and clicks drill from province to district', async ({ page }) => {
  await openPortal(page)
  await page.locator('[data-boundaries-drawn="true"]').waitFor()
  const box = (await page.locator('.map').boundingBox())!
  // The fixture country spans the map's width; its first quarter is District One, in province Alpha.
  const x = box.x + box.width * 0.15
  const y = box.y + box.height / 2
  const crumbs = page.getByRole('navigation', { name: 'Selected place' }).getByRole('listitem')

  const popup = page.locator('.maplibregl-popup')
  // Pointing at a district shows nothing yet; the popup waits for a click.
  await page.mouse.move(x - 5, y)
  await page.mouse.move(x, y, { steps: 3 })
  await page.waitForTimeout(300)
  await expect(popup).toHaveCount(0)

  await page.mouse.click(x, y)
  await expect(popup.locator('strong')).toHaveText('District One')
  await expect(crumbs).toHaveText(['Pakistan', 'Alpha'])
  await page.mouse.click(x, y)
  await expect(crumbs).toHaveText(['Pakistan', 'Alpha', 'District One'])
  // The popup stays open when the pointer moves away, until it is closed.
  await page.mouse.move(box.x + box.width - 30, box.y + box.height - 30, { steps: 3 })
  await expect(popup).toHaveCount(1)
  await popup.getByRole('button', { name: 'Close popup' }).click()
  await expect(popup).toHaveCount(0)
})

test('clicking the map outside every district clears the selection', async ({ page }) => {
  await openPortal(page, '/?place=PK1')
  await page.locator('[data-boundaries-drawn="true"]').waitFor()
  const crumbs = page.getByRole('navigation', { name: 'Selected place' }).getByRole('listitem')
  await expect(crumbs).toHaveText(['Pakistan', 'Alpha'])
  // The map has zoomed to province Alpha, which is taller than it is wide, so the left edge is outside it.
  await page.waitForTimeout(1200)
  const box = (await page.locator('.map').boundingBox())!
  await page.mouse.click(box.x + 40, box.y + box.height / 2)
  await expect(crumbs).toHaveText(['Pakistan'])
})
