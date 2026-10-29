import { expect, test, type Page } from '@playwright/test'
import { openPortal } from './helpers'

const CHART = {
  id: 'calendar-punjab', kind: 'calendar', unit: '', time: false, categories: [], series: [],
  title: 'In Punjab, 1 of 3 crops should be sown earlier than before',
  rows: [
    {
      crop: 'Wheat', changed: true, sown_earlier: true, reason: 'Timely sowing avoids severe spring heat.',
      traditional: { text: 'Oct–Dec sowing → Mar–Apr harvest', sowing: [[9, 12]], harvest: [[2, 4]] },
      adjusted: { text: 'Oct–Nov sowing → Mar–Apr harvest', sowing: [[9, 11]], harvest: [[2, 4]] },
    },
    {
      crop: 'Sugarcane', changed: false, sown_earlier: false, reason: 'Calendar remains broadly similar.',
      traditional: { text: 'Feb–Mar / Sep–Oct', sowing: [[1, 3], [8, 10]], harvest: [] },
      adjusted: { text: 'Feb–Mar / Sep–Oct', sowing: [[1, 3], [8, 10]], harvest: [] },
    },
    {
      crop: 'Orchards', changed: true, sown_earlier: false, reason: 'Warmer winters affect chilling.',
      traditional: { text: 'Traditional regional schedule', sowing: [], harvest: [] },
      adjusted: { text: 'Climate-risk adjusted', sowing: [], harvest: [] },
    },
  ],
}

async function mockCalendar(page: Page, extra: object = {}) {
  await page.route('**/api/sections/alpha-section/data**', (route) =>
    route.fulfill({
      json: {
        section_id: 'alpha-section', place_id: 'PK', level_used: 'national', year: null,
        figures: [{ label: 'Crops with a calendar', value: 3, unit: '' }], notes: [], charts: [CHART], ...extra,
      },
    }),
  )
}

test('the crop calendar draws each crop with its traditional and climate-smart dates', async ({ page }) => {
  // The bars grow in on a loop; with reduced motion they hold still, so their widths can be measured.
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await page.clock.setFixedTime(new Date(2026, 9, 5, 12))
  await mockCalendar(page)
  await openPortal(page, '/?section=alpha-section')
  const calendar = page.getByRole('figure', { name: CHART.title })
  await expect(calendar.getByRole('heading', { name: CHART.title })).toBeVisible()
  await expect(calendar.locator('.calendar-month')).toHaveText(['J', 'F', 'M', 'A', 'M', 'J', 'J', 'A', 'S', 'O', 'N', 'D'])

  const wheat = calendar.locator('.calendar-row', { hasText: 'Wheat' })
  await expect(wheat.getByText('Sow earlier')).toBeVisible()
  await expect(wheat.locator('.calendar-bar')).toHaveCount(4)
  const before = (await wheat.getByRole('img', { name: 'Traditional sowing: October to December' }).boundingBox())!
  const after = (await wheat.getByRole('img', { name: 'Climate-smart sowing: October to November' }).boundingBox())!
  expect(after.width).toBeLessThan(before.width)
  expect(Math.abs(after.x - before.x)).toBeLessThan(1)
  expect(after.y).toBeGreaterThan(before.y)

  const sugarcane = calendar.locator('.calendar-row', { hasText: 'Sugarcane' })
  await expect(sugarcane.getByText('No change')).toBeVisible()
  await expect(sugarcane.locator('.calendar-bar')).toHaveCount(4)

  // A calendar given in words, with no months, is shown as its words.
  const orchards = calendar.locator('.calendar-row', { hasText: 'Orchards' })
  await expect(orchards.locator('.calendar-bar')).toHaveCount(0)
  await expect(orchards).toContainText('Traditional regional schedule')
  await expect(orchards).toContainText('Climate-risk adjusted')
})

test('the calendar marks today', async ({ page }) => {
  await page.clock.setFixedTime(new Date(2026, 9, 5, 12))
  await mockCalendar(page)
  await openPortal(page, '/?section=alpha-section')
  const calendar = page.getByRole('figure', { name: CHART.title })
  const track = (await calendar.locator('.calendar-row', { hasText: 'Wheat' }).locator('.calendar-track').boundingBox())!
  const now = (await calendar.locator('.calendar-row', { hasText: 'Wheat' }).locator('.calendar-now').boundingBox())!
  const fraction = (now.x + now.width / 2 - track.x) / track.width
  expect(fraction).toBeGreaterThan(0.75)
  expect(fraction).toBeLessThan(0.78)
  await expect(calendar.getByText('Today')).toBeVisible()
})

test('the calendar has a table of the dates in words, with the reason for each shift', async ({ page }) => {
  await mockCalendar(page)
  await openPortal(page, '/?section=alpha-section')
  const calendar = page.getByRole('figure', { name: CHART.title })
  await calendar.getByTitle('Show table').click()
  const row = calendar.getByRole('row', { name: /Wheat/ })
  await expect(row).toContainText('Oct–Dec sowing → Mar–Apr harvest')
  await expect(row).toContainText('Oct–Nov sowing → Mar–Apr harvest')
  await expect(row).toContainText('Timely sowing avoids severe spring heat.')
})

test('in the full view each crop shows why its dates change', async ({ page }) => {
  await mockCalendar(page)
  await openPortal(page, '/?section=alpha-section')
  const panel = page.locator('.panel')
  await expect(panel.locator('.calendar-reason')).toHaveCount(0)
  await page.getByRole('button', { name: 'Open charts in full view' }).click()
  const full = page.getByRole('region', { name: 'Charts in full view' })
  await expect(full.locator('.calendar-reason')).toHaveText([
    'Timely sowing avoids severe spring heat.', 'Calendar remains broadly similar.', 'Warmer winters affect chilling.',
  ])
})

test('figures that come from the province say so when a district is selected', async ({ page }) => {
  await mockCalendar(page, { place_id: 'PK1', level_used: 'province' })
  await openPortal(page, '/?section=alpha-section&place=PK101')
  await expect(page.locator('.panel').getByText('These are for Alpha, the province District One is in.')).toBeVisible()
  await expect(page.getByText('National figures only')).toHaveCount(0)
})
