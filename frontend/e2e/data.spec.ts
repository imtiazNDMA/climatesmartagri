import { expect, test, type Page } from '@playwright/test'
import { mockBasemap, mockTiles, openPortal } from './helpers'

const YEARS = [2000, 2001, 2002, 2003, 2004, 2005, 2006, 2007, 2008, 2009, 2010]

function sectionData(year: number | null) {
  return {
    section_id: 'alpha-section', place_id: 'PK', level_used: 'national', year,
    figures: [
      { label: 'Area equipped', value: 16725843, unit: 'ha' },
      { label: 'Share irrigated', value: 79.99, unit: '%' },
      { label: 'Area irrigated', value: null, unit: 'ha' },
    ],
    notes: ['Totals from 112 districts.'],
    charts: [
      {
        id: 'trend', title: 'Demand and supply', kind: 'line', unit: 'Mt', time: true, categories: YEARS,
        series: [
          { name: 'Demand', slot: 1, values: YEARS.map((y) => y - 1990) },
          { name: 'Supply', slot: 3, values: YEARS.map((y) => 2012 - y) },
        ],
      },
      {
        id: 'ranking', title: 'Area by province', kind: 'bar', unit: 'ha', time: false, horizontal: true,
        highlight: null, categories: ['Sindh', 'Punjab'], series: [{ name: 'Area', slot: 1, values: [30, 20] }],
      },
    ],
  }
}

async function mockSectionData(page: Page) {
  await page.route('**/api/sections/alpha-section/data**', (route) => {
    const year = new URL(route.request().url()).searchParams.get('year')
    return route.fulfill({ json: sectionData(year ? Number(year) : 2010) })
  })
}

test('figures are formatted, name their year, and show notes', async ({ page }) => {
  await mockSectionData(page)
  await openPortal(page, '/?section=alpha-section')
  await expect(page.getByRole('heading', { name: 'Figures for Pakistan, 2010' })).toBeVisible()
  await expect(page.getByText('16,725,843 ha')).toBeVisible()
  await expect(page.getByText('79.99 %')).toBeVisible()
  await expect(page.getByText('Not reported')).toBeVisible()
  await expect(page.getByText('Totals from 112 districts.')).toBeVisible()
})

test('charts draw with a title, a legend and a table view', async ({ page }) => {
  await mockSectionData(page)
  await openPortal(page, '/?section=alpha-section')
  const trend = page.getByRole('figure', { name: 'Demand and supply' })
  await expect(trend).toBeVisible()
  await expect(trend.locator('svg')).toContainText('Demand')
  await expect(trend.locator('svg')).toContainText('Supply')
  await expect(page.getByRole('figure', { name: 'Area by province' }).locator('svg')).toContainText('Sindh')

  await trend.getByText('Show table').click()
  const rows = trend.getByRole('row')
  await expect(rows).toHaveCount(YEARS.length + 1)
  await expect(rows.nth(1)).toHaveText(/2000\s*10\s*12/)
})

test('a chart marks the year on the time slider, and follows it', async ({ page }) => {
  await mockSectionData(page)
  await openPortal(page, '/?section=alpha-section')
  const plot = page.getByRole('figure', { name: 'Demand and supply' }).locator('.chart-plot')
  await expect(plot.locator('svg')).toContainText('2010')
  await page.getByRole('group', { name: 'Year' }).getByRole('button', { name: 'Previous year' }).click()
  await expect(page.getByRole('heading', { name: 'Figures for Pakistan, 2009' })).toBeVisible()
  await expect(plot).toHaveAttribute('data-marked-year', '2009')
})

test('clicking a chart sets the year', async ({ page }) => {
  await mockSectionData(page)
  await openPortal(page, '/?section=alpha-section')
  const plot = page.getByRole('figure', { name: 'Demand and supply' }).locator('.chart-plot')
  await expect(plot).toHaveAttribute('data-marked-year', '2010')
  const box = (await plot.boundingBox())!
  await page.mouse.click(box.x + box.width * 0.5, box.y + box.height * 0.6)
  const slider = page.getByRole('group', { name: 'Year' }).getByRole('slider')
  await expect.poll(async () => Number(await slider.inputValue())).toBeLessThan(2009)
  await expect.poll(async () => Number(await slider.inputValue())).toBeGreaterThan(2001)
})

test('a section with figures but no charts for the place says so', async ({ page }) => {
  await page.route('**/api/sections/alpha-section/data**', (route) =>
    route.fulfill({ json: { ...sectionData(2010), figures: [], charts: [], notes: ['No figures are reported for Alpha.'] } }),
  )
  await openPortal(page, '/?section=alpha-section')
  await expect(page.getByText('No figures are reported for Alpha.')).toBeVisible()
  await expect(page.getByText('No charts for this selection.')).toBeVisible()
})

test('a shape layer draws from its own data, with a legend and hover labels', async ({ page }) => {
  const requested: string[] = []
  page.on('request', (request) => {
    if (request.url().includes('/api/layers/')) requested.push(request.url())
  })
  await openPortal(page)
  await page.locator('[data-boundaries-drawn="true"]').waitFor()
  await page.getByRole('button', { name: 'Beta section' }).click()
  await page.getByRole('switch', { name: 'Fake shapes' }).check()
  await page.getByRole('button', { name: 'Beta section' }).click()

  const active = page.getByRole('region', { name: 'Active layers' })
  await expect(active.getByRole('listitem')).toHaveText([/Fake shapes/])
  await expect(active.getByText('Could not load')).toHaveCount(0)
  const legend = page.getByRole('region', { name: 'Legend' })
  await expect(legend).toContainText('Kind A')
  await expect(legend).toContainText('Kind B')
  expect(requested.some((url) => url.includes('/api/layers/fake-shapes/geojson'))).toBe(true)

  // The mocked shape covers the west half of the fixture country, where District One is.
  const box = (await page.locator('.map').boundingBox())!
  const x = box.x + box.width * 0.15
  const y = box.y + box.height / 2
  const popup = page.locator('.maplibregl-popup')
  await expect(async () => {
    await page.mouse.move(x - 6, y)
    await page.mouse.move(x, y, { steps: 3 })
    await expect(popup).toContainText('District One', { timeout: 500 })
    await expect(popup).toContainText('Kind: A', { timeout: 500 })
  }).toPass()
})

test('a shape layer whose data cannot be loaded shows a warning', async ({ page }) => {
  await mockBasemap(page)
  await mockTiles(page)
  await page.goto('/')
  await page.getByRole('navigation', { name: 'Sections' }).waitFor()
  await page.getByRole('button', { name: 'Beta section' }).click()
  await page.getByRole('switch', { name: 'Fake shapes' }).check()
  await expect(page.getByRole('region', { name: 'Active layers' }).getByText('Could not load')).toBeVisible()
})
