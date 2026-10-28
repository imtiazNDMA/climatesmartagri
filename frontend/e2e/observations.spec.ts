import { expect, test } from '@playwright/test'
import { openPortal } from './helpers'

/** Give the fixture's yearly section and layer a sparse series, the way a real collection can have. */
async function sparseSeries(page: import('@playwright/test').Page) {
  await page.route('**/api/catalogue', async (route) => {
    const catalogue = await (await route.fetch()).json()
    const years = { first: 2000, last: 2010, available: [2000, 2005, 2010] }
    for (const section of catalogue.sections) {
      if (section.id === 'alpha-section') Object.assign(section, { years })
    }
    for (const layer of catalogue.layers) {
      if (layer.id === 'fake-yearly') Object.assign(layer, { years })
    }
    await route.fulfill({ json: catalogue })
  })
}

test('the time slider moves between the observations that exist', async ({ page }) => {
  await sparseSeries(page)
  await openPortal(page, '/?section=alpha-section')
  const slider = page.getByRole('group', { name: 'Year' })
  const thumb = slider.getByRole('slider')

  // The latest observation is on show to begin with.
  await expect(thumb).toHaveAttribute('aria-valuetext', '2010')

  await slider.getByRole('button', { name: 'Previous year' }).click()
  await expect(thumb).toHaveAttribute('aria-valuetext', '2005')
  await expect(page).toHaveURL(/year=2005/)

  await slider.getByRole('button', { name: 'Previous year' }).click()
  await expect(thumb).toHaveAttribute('aria-valuetext', '2000')
  await expect(slider.getByRole('button', { name: 'Previous year' })).toBeDisabled()

  await slider.getByRole('button', { name: 'Next year' }).click()
  await expect(thumb).toHaveAttribute('aria-valuetext', '2005')
})

test('a year the series does not have is moved to the nearest observation', async ({ page }) => {
  await sparseSeries(page)
  await openPortal(page, '/?section=alpha-section&year=2007')
  await expect(page.getByRole('group', { name: 'Year' }).getByRole('slider')).toHaveAttribute(
    'aria-valuetext',
    '2005',
  )
  await expect(page).toHaveURL(/year=2005/)
})

test('playback walks the observations and comes back to the first', async ({ page }) => {
  await sparseSeries(page)
  await openPortal(page, '/?section=alpha-section')
  const slider = page.getByRole('group', { name: 'Year' })
  await slider.getByRole('button', { name: 'Play' }).click()
  await expect(slider.getByRole('slider')).toHaveAttribute('aria-valuetext', '2000', { timeout: 5000 })
  await slider.getByRole('button', { name: 'Pause' }).click()
})

const PIXEL = Buffer.from(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==',
  'base64',
)

test('two land layers from the observation each draw from their own mosaic of the same year', async ({ page }) => {
  const years = { first: 2000, last: 2010 }
  const mpcLayer = (id: string, title: string) => ({
    id, title, section_id: 'alpha-section', kind: 'raster', status: 'ready', tile_source: 'mpc',
    years, max_zoom: 14, default_opacity: 0.85, tile_url: null, bounds: null,
    legend: { type: 'classes', items: [{ colour: '#397d49', label: title, value: '2' }] },
  })
  await page.route('**/api/catalogue', async (route) => {
    const catalogue = await (await route.fetch()).json()
    catalogue.layers.push(mpcLayer('mpc-all', 'Annual land classification'), mpcLayer('mpc-trees', 'Trees'))
    await route.fulfill({ json: catalogue })
  })
  await page.route('**/api/land-cover/observation**', (route) => {
    return route.fulfill({
      json: {
        year: 2010, collection: 'io-lulc-annual-v02', search_id: 'pc1.1.abc', item_ids: ['42Q-2010'],
        tiles: {
          'mpc-all': 'https://mpc.test/all/{z}/{x}/{y}.png',
          'mpc-trees': 'https://mpc.test/trees/{z}/{x}/{y}.png',
        },
        bounds: [60, 23, 79, 37], attribution: 'Esri / Impact Observatory / Microsoft Planetary Computer',
      },
    })
  })
  let outlineAsked = false
  await page.route('**/api/land-cover/outline', (route) => {
    outlineAsked = true
    return route.fulfill({
      json: {
        type: 'Feature', properties: {},
        geometry: { type: 'Polygon', coordinates: [[[60, 23], [79, 23], [79, 37], [60, 37], [60, 23]]] },
      },
    })
  })
  const mosaics = new Set<string>()
  await page.route('https://mpc.test/**', (route) => {
    mosaics.add(new URL(route.request().url()).pathname.split('/')[1])
    return route.fulfill({ status: 200, contentType: 'image/png', body: PIXEL })
  })

  await openPortal(page, '/?section=alpha-section&layers=mpc-all:0.85,mpc-trees:0.85&year=2010')
  await page.locator('[data-map-ready="true"]').waitFor()

  await expect.poll(() => [...mosaics].sort()).toEqual(['all', 'trees'])
  // Tiles are cut to the country's outline before they are drawn.
  expect(outlineAsked).toBe(true)
  await expect(page.getByRole('region', { name: 'Active layers' }).getByText('Could not load')).toHaveCount(0)
})

test('where the classification has no data the map is simply empty, not an error', async ({ page }) => {
  const years = { first: 2000, last: 2010 }
  await page.route('**/api/catalogue', async (route) => {
    const catalogue = await (await route.fetch()).json()
    catalogue.layers.push({
      id: 'mpc-all', title: 'Annual land classification', section_id: 'alpha-section', kind: 'raster',
      status: 'ready', tile_source: 'mpc', years, max_zoom: 14, default_opacity: 0.85, tile_url: null, bounds: null,
      legend: { type: 'classes', items: [{ colour: '#397d49', label: 'Trees', value: '2' }] },
    })
    await route.fulfill({ json: catalogue })
  })
  await page.route('**/api/land-cover/observation**', (route) => route.fulfill({
    json: {
      year: 2010, collection: 'io-lulc-annual-v02', search_id: 'pc1.1.abc', item_ids: ['42Q-2010'],
      tiles: { 'mpc-all': 'https://mpc.test/all/{z}/{x}/{y}.png' },
      bounds: [60, 23, 79, 37], attribution: 'Esri / Impact Observatory / Microsoft Planetary Computer',
    },
  }))
  await page.route('**/api/land-cover/outline', (route) => route.fulfill({
    json: {
      type: 'Feature', properties: {},
      geometry: { type: 'Polygon', coordinates: [[[60, 23], [79, 23], [79, 37], [60, 37], [60, 23]]] },
    },
  }))
  let asked = 0
  await page.route('https://mpc.test/**', (route) => {
    asked += 1
    return route.fulfill({ status: 404, body: 'Not Found' })
  })

  await openPortal(page, '/?section=alpha-section&layers=mpc-all:0.85&year=2010')
  await page.locator('[data-map-ready="true"]').waitFor()

  await expect.poll(() => asked).toBeGreaterThan(0)
  await page.waitForTimeout(1000)
  await expect(page.getByRole('region', { name: 'Active layers' }).getByText('Could not load')).toHaveCount(0)
})
