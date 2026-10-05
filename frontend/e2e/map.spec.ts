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
