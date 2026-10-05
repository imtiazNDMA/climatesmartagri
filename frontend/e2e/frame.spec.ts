import { expect, test } from '@playwright/test'
import { mockBasemap, openPortal } from './helpers'

test('opens a section and closes it so the map takes the full width', async ({ page }) => {
  await openPortal(page)
  const map = page.locator('.map-area')
  const closedWidth = (await map.boundingBox())!.width

  await page.getByRole('button', { name: 'Alpha section' }).click()
  await expect(page.getByRole('heading', { name: 'Alpha section' })).toBeVisible()
  expect((await map.boundingBox())!.width).toBeLessThan(closedWidth)

  await page.getByRole('button', { name: 'Alpha section' }).click()
  await expect(page.getByRole('heading', { name: 'Alpha section' })).toBeHidden()
  expect((await map.boundingBox())!.width).toBe(closedWidth)
})

test('lists every section in catalogue order and marks coming-soon ones', async ({ page }) => {
  await openPortal(page)
  const buttons = page.getByRole('navigation', { name: 'Sections' }).locator('button[data-section]')
  await expect(buttons).toHaveCount(5)
  await expect(buttons.nth(0)).toHaveAttribute('aria-label', 'Alpha section')
  await expect(buttons.nth(2)).toHaveAttribute('aria-label', 'Later section (coming soon)')
})

test('shows the coming-soon state', async ({ page }) => {
  await openPortal(page)
  await page.getByRole('button', { name: 'Later section (coming soon)' }).click()
  await expect(page.getByText('Coming soon')).toBeVisible()
  await expect(page.getByText('Will show things later.')).toBeVisible()
})

test('shows the no-data state in every block', async ({ page }) => {
  await openPortal(page)
  await page.getByRole('button', { name: 'Empty section' }).click()
  await expect(page.getByRole('switch', { name: 'Fake empty' })).toBeDisabled()
  await expect(page.getByText('Data not loaded yet')).toHaveCount(3)
})

test('layer switches turn layers on and mark the section in the rail', async ({ page }) => {
  await openPortal(page)
  await page.getByRole('button', { name: 'Alpha section' }).click()
  await page.getByRole('switch', { name: 'Fake yearly' }).check()
  await page.getByRole('button', { name: 'Alpha section' }).click()
  await expect(page.locator('button[data-section="alpha-section"] .rail-dot')).toBeVisible()
  await expect(page.locator('button[data-section="beta-section"] .rail-dot')).toHaveCount(0)
})

test('says "National figures only" when the section has no figures at the selected level', async ({ page }) => {
  await page.route('**/api/sections/beta-section/data**', (route) =>
    route.fulfill({
      json: {
        section_id: 'beta-section', place_id: 'PK', level_used: 'national', year: null,
        figures: [{ label: 'Total', value: 12, unit: 'Mt' }], charts: [],
      },
    }),
  )
  await openPortal(page, '/?section=beta-section&place=PK1')
  await expect(page.getByText('National figures only')).toBeVisible()
  await expect(page.getByText('12 Mt')).toBeVisible()
})

test('opens the About dialog', async ({ page }) => {
  await openPortal(page)
  await page.getByRole('button', { name: 'About' }).click()
  await expect(page.getByRole('dialog')).toContainText('Data sources')
})

test('shows a full-screen message when the backend is off, and recovers on retry', async ({ page }) => {
  await mockBasemap(page)
  // A regex on the port, because the glob **/api/** would also block the app's own src/api modules.
  const backendCalls = /:5183\/api\//
  await page.route(backendCalls, (route) => route.abort())
  await page.goto('/')
  await expect(page.getByRole('heading', { name: "The portal can't reach its data service" })).toBeVisible()
  await expect(page.getByText('npm run dev')).toBeVisible()

  await page.unroute(backendCalls)
  await page.getByRole('button', { name: 'Try again' }).click()
  await expect(page.getByRole('navigation', { name: 'Sections' })).toBeVisible()
})

test('shows a notice when boundaries are not loaded', async ({ page }) => {
  await page.route('**/api/places/boundaries**', (route) =>
    route.fulfill({ status: 404, json: { detail: { message: 'none', reason: 'no-data' } } }),
  )
  await openPortal(page)
  await expect(page.getByText('Boundaries are not loaded')).toBeVisible()
  await page.getByRole('button', { name: 'Alpha section' }).click()
  await expect(page.getByRole('heading', { name: 'Alpha section' })).toBeVisible()
})

test('the panel covers the map on a narrow screen and has a close button', async ({ page }) => {
  await page.setViewportSize({ width: 800, height: 900 })
  await openPortal(page)
  await page.getByRole('button', { name: 'Alpha section' }).click()
  const panel = (await page.locator('.panel').boundingBox())!
  expect(panel.x).toBeGreaterThanOrEqual(56)
  expect(panel.x + panel.width).toBe(800)
  await page.getByRole('button', { name: 'Close panel' }).click()
  await expect(page.locator('.panel')).toHaveCount(0)
})

test('a no-data section without layers still says "Data not loaded yet" in all three blocks', async ({ page }) => {
  await openPortal(page)
  await page.getByRole('button', { name: 'Bare section' }).click()
  await expect(page.getByText('Data not loaded yet')).toHaveCount(3)
})

test('shows a banner when the backend is lost while in use, keeps the view, and recovers', async ({ page }) => {
  await openPortal(page)
  await page.getByRole('button', { name: 'Alpha section' }).click()
  const backendCalls = /:5183\/api\//
  await page.route(backendCalls, (route) => route.abort())
  await expect(page.getByText('The portal has lost its data service')).toBeVisible({ timeout: 15000 })
  await expect(page.getByRole('heading', { name: 'Alpha section' })).toBeVisible()

  await page.unroute(backendCalls)
  await page.getByRole('button', { name: 'Check again' }).click()
  await expect(page.getByText('The portal has lost its data service')).toHaveCount(0)
})

test('says why boundaries could not be loaded', async ({ page }) => {
  await page.route('**/api/places/boundaries**', (route) =>
    route.fulfill({ status: 404, json: { detail: { message: 'none', reason: 'no-data' } } }),
  )
  await page.route('**/api/health', (route) =>
    route.fulfill({
      json: {
        status: 'ok', boundaries_loaded: false, layers: {},
        boundaries_error: 'provinces.geojson: feature 3 has no name',
      },
    }),
  )
  await openPortal(page)
  await expect(page.getByText('provinces.geojson: feature 3 has no name')).toBeVisible()
})
