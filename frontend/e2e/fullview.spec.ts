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
            end_labels: true, categories: YEARS,
            series: [
              { name: 'Food needed', slot: 1, values: YEARS.map((y) => y - 1990), emphasis: 'strong' },
              { name: 'Food available', slot: 3, values: YEARS.map((y) => 2012 - y) },
            ],
          },
          {
            id: 'growth', title: 'Nitrous oxide grew fastest', kind: 'bar', unit: 'times', time: false,
            horizontal: true, bar_slots: [1, 2, 3],
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

test('the full view tells the story: headline, key figures and notes', async ({ page }) => {
  await mockSectionData(page)
  await openPortal(page, '/?section=alpha-section&view=charts')
  const full = page.getByRole('region', { name: 'Charts in full view' })
  await expect(full.getByRole('heading', { level: 2 })).toHaveText('Alpha section')
  await expect(full.getByText('Pakistan, 2010')).toBeVisible()
  await expect(full.getByRole('heading', { name: 'Food needs rise faster than supply' })).toBeVisible()
  // Nothing sits between a chart's headline and its plot.
  await expect(full.locator('figcaption > *')).toHaveCount(2)
  await expect(full.getByText('386.06 million')).toBeVisible()
  await expect(full.getByText('A note about the data.')).toBeVisible()

  const trend = full.getByRole('figure', { name: 'Food needs rise faster than supply' })
  // In the full view the lines are labelled where they end.
  await expect(trend.locator('.chart-plot svg')).toContainText('Food needed')
  await expect(trend.locator('.chart-plot svg')).toContainText('Food available')
  await expect(full.getByRole('figure', { name: 'Nitrous oxide grew fastest' }).locator('.chart-plot svg')).toContainText('6.8×')
  const plot = (await trend.locator('.chart-plot').boundingBox())!
  expect(plot.height).toBeGreaterThan(300)
})

test('one chart can be maximized to fill the full view, and minimized again', async ({ page }) => {
  await mockSectionData(page)
  await openPortal(page, '/?section=alpha-section&view=charts')
  const full = page.getByRole('region', { name: 'Charts in full view' })
  const growth = full.getByRole('figure', { name: 'Nitrous oxide grew fastest' })
  const before = (await growth.boundingBox())!
  await full.getByRole('button', { name: 'Maximize: Nitrous oxide grew fastest' }).click()
  await expect(full.getByRole('figure')).toHaveCount(1)
  // Alone, it takes the height the other chart was using, and is redrawn at that size, not stretched.
  await expect.poll(async () => (await growth.boundingBox())!.height).toBeGreaterThan(before.height + 60)
  await expect
    .poll(async () => {
      const plot = (await growth.locator('.chart-plot').boundingBox())!
      const drawing = (await growth.locator('.chart-plot svg').boundingBox())!
      return Math.abs(plot.height - drawing.height)
    })
    .toBeLessThan(2)
  await full.getByRole('button', { name: 'Minimize: Nitrous oxide grew fastest' }).click()
  await expect(full.getByRole('figure')).toHaveCount(2)

  await full.getByRole('button', { name: 'Maximize: Food needs rise faster than supply' }).click()
  await expect(full.getByRole('figure')).toHaveCount(1)
  await page.keyboard.press('Escape')
  await expect(full.getByRole('figure')).toHaveCount(2)
})

test('a chart in the panel can be maximized straight into the full view', async ({ page }) => {
  await mockSectionData(page)
  await openPortal(page, '/?section=alpha-section')
  await page.locator('.panel').getByRole('button', { name: 'Maximize: Nitrous oxide grew fastest' }).click()
  const full = page.getByRole('region', { name: 'Charts in full view' })
  await expect(full.getByRole('figure')).toHaveCount(1)
  await expect(full.getByRole('figure', { name: 'Nitrous oxide grew fastest' })).toBeVisible()
  await full.getByRole('button', { name: 'Back to map' }).click()
  await page.getByRole('button', { name: 'Open charts in full view' }).click()
  await expect(full.getByRole('figure')).toHaveCount(2)
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

test('side titles never run into each other, however wide the full view is', async ({ page }) => {
  const years = [2026, 2027]
  await page.route('**/api/sections/alpha-section/data**', (route) => route.fulfill({
    json: {
      section_id: 'alpha-section', place_id: 'PK', level_used: 'national', year: 2027, figures: [], notes: [],
      charts: [
        {
          id: 'water-buffer', title: 'Higher efficiency protects the water buffer', kind: 'balance', unit: '', time: true,
          categories: years,
          series: [
            { name: '35% efficiency', slot: 2, values: [-23, -38.7] },
            { name: '70% efficiency', slot: 4, values: [43, 34.6] },
          ],
          balance: {
            available: [109, 107.9], needed: [[132, 146.6], [66, 73.3]],
            negative: 'Water deficit', positive: 'Water buffer', zero: 'Water limit',
            negative_word: 'deficit', positive_word: 'buffer',
          },
        },
        {
          id: 'irrigation-source', title: "Where each province's irrigation water comes from", kind: 'diverging',
          unit: '%', time: false, categories: [], series: [],
          sides: [{ label: 'Groundwater', colour: '#3b4cc0' }, { label: 'Surface water', colour: '#b40426' }],
          splits: [
            { name: 'Khyber Pakhtunkhwa', left: 17.6, right: 82.4, weight: 5, highlight: false },
            { name: 'Sindh', left: 4.1, right: 95.9, weight: 13, highlight: false },
          ],
        },
      ],
    },
  }))
  const apart = (a: DOMRect, b: DOMRect) => a.right <= b.left || b.right <= a.left || a.bottom <= b.top || b.bottom <= a.top
  for (const width of [1280, 1440, 1600, 1920]) {
    await page.setViewportSize({ width, height: 1000 })
    await openPortal(page, '/?section=alpha-section&view=charts')
    const full = page.getByRole('region', { name: 'Charts in full view' })
    await full.locator('.balance-zone').first().waitFor()
    const report = await full.evaluate((view) => {
      const rects = (selector: string) => [...view.querySelectorAll<HTMLElement>(selector)].map((e) => {
        // A range measures the words themselves, which may spill out of a box that is too small for them.
        const range = document.createRange()
        range.selectNodeContents(e)
        const r = range.getBoundingClientRect()
        return { left: r.left, right: r.right, top: r.top, bottom: r.bottom } as DOMRect
      })
      return { zones: rects('.balance-zone'), sides: rects('.diverging-head .diverging-side'), names: rects('.balance-name, .diverging-name') }
    })
    expect(apart(report.zones[0], report.zones[1]), `water balance titles at ${width}px`).toBe(true)
    expect(apart(report.sides[0], report.sides[1]), `irrigation side titles at ${width}px`).toBe(true)
  }
})
