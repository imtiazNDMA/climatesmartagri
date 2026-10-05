import type { Page } from '@playwright/test'

const BLANK_STYLE = {
  version: 8,
  sources: {},
  layers: [{ id: 'background', type: 'background', paint: { 'background-color': '#eef1f4' } }],
}
const TRANSPARENT_PNG = Buffer.from(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==',
  'base64',
)

/** Serve a blank background map so tests never need the internet. */
export async function mockBasemap(page: Page) {
  await page.route('https://basemap.test/**', (route) => route.fulfill({ json: BLANK_STYLE }))
}

/** The fixture backend has no tile providers; answer tile requests with an empty image. */
export async function mockTiles(page: Page) {
  await page.route('**/api/tiles/**', (route) =>
    route.fulfill({ status: 200, contentType: 'image/png', body: TRANSPARENT_PNG }),
  )
}

export async function openPortal(page: Page, path = '/') {
  await mockBasemap(page)
  await mockTiles(page)
  await page.goto(path)
  await page.getByRole('navigation', { name: 'Sections' }).waitFor()
}
