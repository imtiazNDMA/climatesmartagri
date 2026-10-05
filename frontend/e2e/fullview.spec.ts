import { expect, test, type Page } from '@playwright/test'
import { openPortal } from './helpers'

const YEARS = [2000, 2001, 2002, 2003, 2004, 2005, 2006, 2007, 2008, 2009, 2010]

async function mockSectionData(page: Page) {
  await page.route('**/api/sections/alpha-section/data**', (route) => {
    const year = Number(new URL(route.request().url()).searchParams.get('year') ?? 2010)
    return route.fulfill({
      json: {
        section_id: 'alpha-section', place_id: 'PK', level_used: 'national', year,
        figures: [
          { label: 'Food needed', value: 168.7, unit: '' },
          { label: 'Population', value: 386.06, unit: 'million' },
        ],
        notes: ['A note about the data.'],
        charts: [
          {
            id: 'trend', title: 'Food needs rise faster than supply', kind: 'line', unit: '', time: true,
            subtitle: 'The dark line is the food the country needs.', end_labels: true, categories: YEARS,
            series: [
              { name: 'Food needed', slot: 1, values: YEARS.map((y) => y - 1990), emphasis: 'strong' },
              { name: 'Food available', slot: 3, values: YEARS.map((y) => 2012 - y) },
            ],
          },
          {
            id: 'growth', title: 'Nitrous oxide grew fastest', kind: 'bar', unit: 'times', time: false,
            subtitle: 'How many times larger each gas became.', horizontal: true, bar_slots: [1, 2, 3],
            categories: ['Carbon dioxide', 'Methane', 'Nitrous oxide'],
            series: [{ name: 'Growth', slot: 1, values: [2.9, 2.4, 6.8] }],
          },
        ],
      },
    })
  })
}

test('charts open in a full view that replaces the map, and go back', async ({ page }) => {
  await mockSectionData(page)
  await openPortal(page, '/?section=alpha-section')
  await page.locator('[data-map-ready="true"]').waitFor()
  const full = page.getByRole('region', { name: 'Charts in full view' })
  await expect(full).toHaveCount(0)

  await page.getByRole('button', { name: 'Open charts in full view' }).click()
  await expect(full).toBeVisible()
  await expect(page).toHaveURL(/view=charts/)
  // The full view takes the map's place: the map and its controls are out of sight.
  const area = (await page.locator('.map-area').boundingBox())!
  const view = (await full.boundingBox())!
  expect(view.width).toBe(area.width)
  await expect(page.locator('.map')).toBeHidden()
  await expect(page.getByRole('searchbox', { name: 'Search place' })).toBeHidden()
  // It stops above the year slider, so the slider never covers a chart.
  const slider = (await page.getByRole('group', { name: 'Year' }).boundingBox())!
  expect(view.y + view.height).toBeLessThanOrEqual(slider.y)

  await full.getByRole('button', { name: 'Back to map' }).click()
  await expect(full).toHaveCount(0)
  await expect(page).not.toHaveURL(/view=charts/)
  await expect(page.locator('.map')).toBeVisible()
  await expect(page.getByRole('searchbox', { name: 'Search place' })).toBeVisible()
})

test('the full view tells the story: headline, how to read it, key figures and notes', async ({ page }) => {
  await mockSectionData(page)
  await openPortal(page, '/?section=alpha-section&view=charts')
  const full = page.getByRole('region', { name: 'Charts in full view' })
  await expect(full.getByRole('heading', { level: 2 })).toHaveText('Alpha section')
  await expect(full.getByText('Pakistan, 2010')).toBeVisible()
  await expect(full.getByRole('heading', { name: 'Food needs rise faster than supply' })).toBeVisible()
  await expect(full.getByText('The dark line is the food the country needs.')).toBeVisible()
  await expect(full.getByText('386.06 million')).toBeVisible()
  await expect(full.getByText('A note about the data.')).toBeVisible()

  const trend = full.getByRole('figure', { name: 'Food needs rise faster than supply' })
  // In the full view the lines are labelled where they end.
  await expect(trend.locator('.chart-plot svg')).toContainText('Food needed')
  await expect(trend.locator('.chart-plot svg')).toContainText('Food available')
  await expect(full.getByRole('figure', { name: 'Nitrous oxide grew fastest' }).locator('svg')).toContainText('6.8×')
  const plot = (await trend.locator('.chart-plot').boundingBox())!
  expect(plot.height).toBeGreaterThan(300)
})

test('in the full view the panel points to it and does not repeat the charts', async ({ page }) => {
  await mockSectionData(page)
  await openPortal(page, '/?section=alpha-section&view=charts')
  const panel = page.locator('.panel')
  await expect(panel.getByRole('figure')).toHaveCount(0)
  await expect(panel.getByText('The charts are open in full view.')).toBeVisible()
  await panel.getByRole('button', { name: 'Back to map' }).click()
  await expect(panel.getByRole('figure')).toHaveCount(2)
})

test('the year slider still works in the full view', async ({ page }) => {
  await mockSectionData(page)
  await openPortal(page, '/?section=alpha-section&view=charts')
  const full = page.getByRole('region', { name: 'Charts in full view' })
  await page.getByRole('group', { name: 'Year' }).getByRole('button', { name: 'Previous year' }).click()
  await expect(full.getByText('Pakistan, 2009')).toBeVisible()
})

test('the full view survives a reload and ends when the section is closed', async ({ page }) => {
  await mockSectionData(page)
  await openPortal(page, '/?section=alpha-section')
  await page.getByRole('button', { name: 'Open charts in full view' }).click()
  await page.reload()
  const full = page.getByRole('region', { name: 'Charts in full view' })
  await expect(full).toBeVisible()
  await page.getByRole('button', { name: 'Close panel' }).click()
  await expect(full).toHaveCount(0)
})

test('a section with no charts offers no full view button, and says so if opened by link', async ({ page }) => {
  await openPortal(page, '/?section=empty-section')
  await expect(page.getByRole('button', { name: 'Open charts in full view' })).toHaveCount(0)
  await openPortal(page, '/?section=empty-section&view=charts')
  await expect(page.getByRole('region', { name: 'Charts in full view' })).toContainText('Data not loaded yet')
})
