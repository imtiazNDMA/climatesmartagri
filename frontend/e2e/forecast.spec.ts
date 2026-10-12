import { expect, test, type Page } from '@playwright/test'
import { openPortal } from './helpers'

const PIXEL = Buffer.from(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==',
  'base64',
)

const SECTION = {
  id: 'forecast', title: 'Weather forecast', icon: 'cloud-sun', order: 9, status: 'ready', kind: 'forecast',
  summary: '', place_levels: ['national'], years: null,
}
const FORECAST = {
  configured: true,
  bbox: [55, 18, 85, 42],
  models: [
    { id: 'model-a', label: 'Model A' },
    { id: 'model-b', label: 'Model B' },
  ],
  groups: [
    { id: 'heat', title: 'Heat' },
    { id: 'rain', title: 'Rain' },
  ],
  layers: [
    {
      id: 'temperature', title: 'Temperature', group: 'heat', unit: '°C', colours: ['#2c7bb6', '#d7191c'],
      min: 0, max: 45, ranges: { '850': [-10, 30] }, levels: { 'model-a': [0, 850], 'model-b': [0] },
    },
    {
      id: 'rain-24h', title: '24-hour rain', group: 'rain', unit: 'mm', colours: ['#cfe1f2', '#2171b5', '#08306b'],
      min: 0, max: 100, ranges: {}, stops: [0, 10, 100], levels: { 'model-b': [0] },
    },
    {
      id: 'old-only', title: 'Old only', group: 'rain', unit: '', colours: ['#ffffff', '#000000'],
      min: 0, max: 1, ranges: {}, levels: {},
    },
  ],
}
// The browser's clock is fixed at 12 Oct 2026 02:00 UTC, so the middle time is the closest.
const TIMES = [
  { time: '2026101118', run: '2026100912' },
  { time: '2026101200', run: '2026100912' },
  { time: '2026101206', run: '2026100900' },
]

interface Mocks {
  tiles: string[]
  timesRequests: string[]
}

async function openWithForecast(page: Page, path = '/', times: unknown = { times: TIMES }, timesStatus = 200) {
  const mocks: Mocks = { tiles: [], timesRequests: [] }
  await page.clock.setFixedTime(new Date('2026-10-12T02:00:00Z'))
  await page.route('**/api/catalogue', async (route) => {
    const catalogue = await (await route.fetch()).json()
    await route.fulfill({ json: { ...catalogue, sections: [...catalogue.sections, SECTION], forecast: FORECAST } })
  })
  await page.route('**/api/forecast/times**', (route) => {
    mocks.timesRequests.push(new URL(route.request().url()).search)
    return route.fulfill({ status: timesStatus, json: times })
  })
  await page.route('**/api/forecast/cog/**', (route) => {
    mocks.tiles.push(new URL(route.request().url()).search)
    return route.fulfill({ status: 200, contentType: 'image/png', body: PIXEL })
  })
  await openPortal(page, path)
  return mocks
}

test('the forecast section lists its layers by group, and marks one with no current data', async ({ page }) => {
  await openWithForecast(page)
  await page.getByRole('button', { name: 'Weather forecast' }).click()
  const panel = page.getByRole('complementary', { name: 'Weather forecast' })
  await expect(panel.getByRole('heading', { level: 4 })).toHaveText(['Heat', 'Rain'])
  await expect(panel.getByRole('switch')).toHaveCount(3)
  await expect(panel.getByRole('switch', { name: 'Old only' })).toBeDisabled()
  await expect(panel).toContainText('No current data from PMD')
  await expect(page.getByRole('group', { name: 'Forecast time' })).toHaveCount(0)
})

test('turning a layer on draws it for the time closest to now, with a key and a time slider', async ({ page }) => {
  const mocks = await openWithForecast(page)
  await page.locator('[data-map-ready="true"]').waitFor()
  await page.getByRole('button', { name: 'Weather forecast' }).click()
  const panel = page.getByRole('complementary', { name: 'Weather forecast' })
  await panel.getByRole('switch', { name: 'Temperature' }).check()

  await expect(panel).toContainText('Forecast for Mon 12 Oct, 05:00 Pakistan time')
  await expect(panel).toContainText('From the model run of 9 Oct 12:00 UTC')
  await expect(page).toHaveURL(/forecast=temperature~model-a~0~2026101200/)
  expect(mocks.timesRequests).toContain('?layer=temperature&model=model-a&level=0')

  const legend = page.getByRole('region', { name: 'Legend' })
  await expect(legend.getByRole('heading', { level: 4 })).toHaveText('Temperature · Model A')
  await expect(legend.locator('.legend-ends')).toHaveText('0 °C45 °C')

  const slider = page.getByRole('group', { name: 'Forecast time' })
  await expect(slider.locator('strong')).toHaveText('Mon 12 Oct, 05:00')
  await expect
    .poll(() => mocks.tiles.some((q) => q.includes('layer=temperature&model=model-a&level=0&time=2026101200')))
    .toBe(true)
  await expect(page.locator('.rail-button[data-section="forecast"] .rail-dot')).toHaveCount(1)
})

test('the model and level can be changed, and a model without the layer cannot be picked', async ({ page }) => {
  const mocks = await openWithForecast(page)
  await page.locator('[data-map-ready="true"]').waitFor()
  await page.getByRole('button', { name: 'Weather forecast' }).click()
  const panel = page.getByRole('complementary', { name: 'Weather forecast' })
  await panel.getByRole('switch', { name: 'Temperature' }).check()

  await panel.getByRole('group', { name: 'Level' }).getByRole('button', { name: '850 hPa' }).click()
  await expect(page).toHaveURL(/forecast=temperature~model-a~850~2026101200/)
  const legend = page.getByRole('region', { name: 'Legend' })
  await expect(legend.getByRole('heading', { level: 4 })).toHaveText('Temperature, 850 hPa · Model A')
  await expect(legend.locator('.legend-ends')).toHaveText('-10 °C30 °C')
  await expect.poll(() => mocks.tiles.some((q) => q.includes('model=model-a&level=850&time=2026101200'))).toBe(true)

  // Model B has temperature at the surface only: the level falls back and its buttons go.
  await panel.getByRole('group', { name: 'Model' }).getByRole('button', { name: 'Model B' }).click()
  await expect(page).toHaveURL(/forecast=temperature~model-b~0~2026101200/)
  await expect(panel.getByRole('group', { name: 'Level' })).toHaveCount(0)

  // Rain comes from Model B alone.
  await panel.getByRole('switch', { name: '24-hour rain' }).check()
  await expect(panel.getByRole('switch', { name: 'Temperature' })).not.toBeChecked()
  await expect(panel.getByRole('group', { name: 'Model' }).getByRole('button', { name: 'Model A' })).toBeDisabled()
  await expect(page).toHaveURL(/forecast=rain-24h~model-b~0/)
  // Uneven colour stops: each colour's value is written under the key, and the unit moves to the heading.
  await expect(legend.getByRole('heading', { level: 4 })).toHaveText('24-hour rain (mm) · Model B')
  await expect(legend.locator('.legend-ends span')).toHaveText(['0', '10', '100'])
})

test('the slider steps through the times, and the layer can be taken off the map', async ({ page }) => {
  const mocks = await openWithForecast(page)
  await page.locator('[data-map-ready="true"]').waitFor()
  await page.getByRole('button', { name: 'Weather forecast' }).click()
  const panel = page.getByRole('complementary', { name: 'Weather forecast' })
  await panel.getByRole('switch', { name: 'Temperature' }).check()
  const slider = page.getByRole('group', { name: 'Forecast time' })

  await slider.getByRole('button', { name: 'Later time' }).click()
  await expect(slider.locator('strong')).toHaveText('Mon 12 Oct, 11:00')
  await expect(page).toHaveURL(/~2026101206/)
  await expect(panel).toContainText('From the model run of 9 Oct 00:00 UTC')
  await expect(slider.getByRole('button', { name: 'Later time' })).toBeDisabled()
  await expect.poll(() => mocks.tiles.some((q) => q.includes('time=2026101206'))).toBe(true)

  await slider.getByRole('button', { name: 'Earlier time' }).click()
  await slider.getByRole('button', { name: 'Earlier time' }).click()
  await expect(slider.locator('strong')).toHaveText('Sun 11 Oct, 23:00')
  await expect(slider.getByRole('button', { name: 'Earlier time' })).toBeDisabled()

  await panel.getByRole('button', { name: 'Remove from map' }).click()
  await expect(page.getByRole('group', { name: 'Forecast time' })).toHaveCount(0)
  await expect(page.getByRole('region', { name: 'Legend' })).toHaveCount(0)
  await expect(page).not.toHaveURL(/forecast=/)
})

test('a link brings the forecast back, and stays on the map with its section closed', async ({ page }) => {
  await openWithForecast(page, '/?section=forecast&forecast=temperature~model-a~850~2026101206')
  const panel = page.getByRole('complementary', { name: 'Weather forecast' })
  await expect(panel.getByRole('switch', { name: 'Temperature' })).toBeChecked()
  await expect(panel.getByRole('group', { name: 'Level' }).getByRole('button', { name: '850 hPa' })).toHaveAttribute(
    'aria-pressed', 'true',
  )
  await expect(page.getByRole('group', { name: 'Forecast time' }).locator('strong')).toHaveText('Mon 12 Oct, 11:00')

  await panel.getByRole('button', { name: 'Close panel' }).click()
  await expect(page.getByRole('group', { name: 'Forecast time' })).toHaveCount(1)
  await expect(page.getByRole('region', { name: 'Legend' })).toContainText('Temperature, 850 hPa')
})

test('a forecast the layer list does not offer is dropped from a link with a notice', async ({ page }) => {
  await openWithForecast(page, '/?forecast=temperature~model-b~850')
  await expect(page.getByText('Ignored from the link: forecast "temperature~model-b~850".')).toBeVisible()
  await expect(page).not.toHaveURL(/forecast=/)
})

test('when PMD is not answering the panel says so and there is no slider', async ({ page }) => {
  await openWithForecast(
    page, '/', { detail: { message: 'PMD could not be reached', reason: 'source-unreachable' } }, 424,
  )
  await page.getByRole('button', { name: 'Weather forecast' }).click()
  const panel = page.getByRole('complementary', { name: 'Weather forecast' })
  await panel.getByRole('switch', { name: 'Temperature' }).check()
  await expect(panel.getByRole('status')).toContainText('PMD’s server is not answering')
  await expect(page.getByRole('group', { name: 'Forecast time' })).toHaveCount(0)
})

test('a model with no recent files says so', async ({ page }) => {
  await openWithForecast(page, '/', { times: [] })
  await page.getByRole('button', { name: 'Weather forecast' }).click()
  const panel = page.getByRole('complementary', { name: 'Weather forecast' })
  await panel.getByRole('switch', { name: 'Temperature' }).check()
  await expect(panel.getByRole('status')).toContainText('PMD has no recent files for this choice.')
})

test('the panel says a time is being fetched until its tiles arrive', async ({ page }) => {
  await openWithForecast(page)
  let release: () => void = () => {}
  const held = new Promise<void>((resolve) => {
    release = resolve
  })
  // Registered last, so it answers before the instant mock: tiles wait, as they do on a first fetch from PMD.
  await page.route('**/api/forecast/cog/**', async (route) => {
    await held
    await route.fulfill({ status: 200, contentType: 'image/png', body: PIXEL })
  })
  await page.locator('[data-map-ready="true"]').waitFor()
  await page.getByRole('button', { name: 'Weather forecast' }).click()
  const panel = page.getByRole('complementary', { name: 'Weather forecast' })
  await panel.getByRole('switch', { name: 'Temperature' }).check()
  await expect(panel.getByText('Fetching this time from PMD…')).toBeVisible()
  release()
  await expect(panel.getByText('Fetching this time from PMD…')).toHaveCount(0)
})

test('a time whose tiles fail says so', async ({ page }) => {
  await openWithForecast(page)
  await page.route('**/api/forecast/cog/**', (route) =>
    route.fulfill({ status: 424, json: { detail: { message: 'PMD could not be reached', reason: 'source-unreachable' } } }),
  )
  await page.locator('[data-map-ready="true"]').waitFor()
  await page.getByRole('button', { name: 'Weather forecast' }).click()
  const panel = page.getByRole('complementary', { name: 'Weather forecast' })
  await panel.getByRole('switch', { name: 'Temperature' }).check()
  await expect(panel.getByRole('alert')).toContainText('This time could not be fetched from PMD')
})

test('the times just ahead of the one on screen are asked for in advance', async ({ page }) => {
  const mocks = await openWithForecast(page, '/?forecast=temperature~model-a~0~2026101118')
  await page.locator('[data-map-ready="true"]').waitFor()
  const warmed = () => mocks.tiles.filter((q) => !q.includes('resampling')).map((q) => q.match(/time=(\d+)/)?.[1])
  await expect.poll(warmed).toEqual(['2026101200', '2026101206'])

  // Stepping on asks for nothing new: both later times were already asked for.
  await page.getByRole('group', { name: 'Forecast time' }).getByRole('button', { name: 'Later time' }).click()
  await expect(page).toHaveURL(/~2026101200/)
  await page.waitForTimeout(300)
  expect(warmed()).toEqual(['2026101200', '2026101206'])
})

test('play steps through the times, waits for one still loading, and wraps round', async ({ page }) => {
  await openWithForecast(page, '/?forecast=temperature~model-a~0~2026101200')
  // The last time's tiles are held back, as on a first fetch from PMD.
  let release: () => void = () => {}
  const held = new Promise<void>((resolve) => {
    release = resolve
  })
  await page.route('**/api/forecast/cog/tiles/**', async (route) => {
    if (route.request().url().includes('time=2026101206')) await held
    await route.fulfill({ status: 200, contentType: 'image/png', body: PIXEL })
  })
  await page.locator('[data-map-ready="true"]').waitFor()
  const slider = page.getByRole('group', { name: 'Forecast time' })
  await expect(slider.locator('strong')).toHaveText('Mon 12 Oct, 05:00')
  await slider.getByRole('button', { name: 'Play' }).click()

  await expect(slider.locator('strong')).toHaveText('Mon 12 Oct, 11:00')
  // It stays on the time that is still loading rather than running on past it.
  await page.waitForTimeout(3000)
  await expect(slider.locator('strong')).toHaveText('Mon 12 Oct, 11:00')
  release()
  await expect(slider.locator('strong')).toHaveText('Sun 11 Oct, 23:00')
  await slider.getByRole('button', { name: 'Pause' }).click()
})
