import { expect, test, type Page } from '@playwright/test'
import { mockBasemap, openPortal } from './helpers'

async function switchOn(page: Page, section: string, layer: string) {
  await page.getByRole('button', { name: section }).click()
  await page.getByRole('switch', { name: layer }).check()
}

test('layers from two sections stack in the active list and the legend', async ({ page }) => {
  await openPortal(page)
  await switchOn(page, 'Alpha section', 'Fake yearly')
  await switchOn(page, 'Beta section', 'Fake static')

  const active = page.getByRole('region', { name: 'Active layers' })
  await expect(active.getByRole('listitem')).toHaveText([/Fake static/, /Fake yearly/])
  const legend = page.getByRole('region', { name: 'Legend' })
  await expect(legend.getByRole('heading')).toHaveText([/Fake static/, /Fake yearly/])
  await expect(legend).toContainText('Yearly class')
  await expect(legend).toContainText('0 – 100 %')
})

test('layers can be reordered, faded, hidden and removed', async ({ page }) => {
  await openPortal(page)
  await switchOn(page, 'Alpha section', 'Fake yearly')
  await switchOn(page, 'Beta section', 'Fake static')
  const active = page.getByRole('region', { name: 'Active layers' })

  await active.getByRole('button', { name: 'Move Fake yearly up' }).click()
  await expect(active.getByRole('listitem')).toHaveText([/Fake yearly/, /Fake static/])
  await expect(page.getByRole('region', { name: 'Legend' }).getByRole('heading')).toHaveText([
    /Fake yearly/, /Fake static/,
  ])

  await active.getByRole('slider', { name: 'Opacity of Fake yearly' }).fill('0.4')
  await expect(page).toHaveURL(/fake-yearly:0\.4/)

  await active.getByRole('button', { name: 'Hide Fake yearly' }).click()
  await expect(active.getByRole('button', { name: 'Show Fake yearly' })).toBeVisible()

  await active.getByRole('button', { name: 'Remove Fake static' }).click()
  await expect(active.getByRole('listitem')).toHaveCount(1)
  await expect(page.getByRole('switch', { name: 'Fake static' })).not.toBeChecked()
})

test('the active list and legend disappear when no layer is active', async ({ page }) => {
  await openPortal(page)
  await expect(page.getByRole('region', { name: 'Active layers' })).toHaveCount(0)
  await expect(page.getByRole('region', { name: 'Legend' })).toHaveCount(0)
})

test('the time slider appears only when something on screen has years', async ({ page }) => {
  await openPortal(page)
  const slider = page.getByRole('group', { name: 'Year' })
  await expect(slider).toHaveCount(0)

  await page.getByRole('button', { name: 'Beta section' }).click()
  await page.getByRole('switch', { name: 'Fake static' }).check()
  await expect(slider).toHaveCount(0)

  await page.getByRole('button', { name: 'Alpha section' }).click()
  await expect(slider).toBeVisible()
  await page.getByRole('button', { name: 'Alpha section' }).click()
  await expect(slider).toHaveCount(0)

  await switchOn(page, 'Alpha section', 'Fake yearly')
  await page.getByRole('button', { name: 'Alpha section' }).click()
  await expect(slider).toBeVisible()
})

test('the time slider steps through years and the legend shows the year on display', async ({ page }) => {
  await openPortal(page)
  await switchOn(page, 'Alpha section', 'Fake yearly')
  const slider = page.getByRole('group', { name: 'Year' })
  const legend = page.getByRole('region', { name: 'Legend' })
  await expect(slider.getByRole('slider')).toHaveValue('2010')
  await expect(legend).toContainText('Fake yearly (2010)')

  await slider.getByRole('button', { name: 'Previous year' }).click()
  await expect(slider.getByRole('slider')).toHaveValue('2009')
  await expect(legend).toContainText('Fake yearly (2009)')
  await expect(page).toHaveURL(/year=2009/)

  await slider.getByRole('button', { name: 'Next year' }).click()
  await expect(slider.getByRole('slider')).toHaveValue('2010')
  await expect(slider.getByRole('button', { name: 'Next year' })).toBeDisabled()
})

test('play steps forward and wraps to the first year', async ({ page }) => {
  await openPortal(page)
  await switchOn(page, 'Alpha section', 'Fake yearly')
  const slider = page.getByRole('group', { name: 'Year' })
  await slider.getByRole('button', { name: 'Play' }).click()
  await expect(slider.getByRole('slider')).toHaveValue('2000', { timeout: 3000 })
  await slider.getByRole('button', { name: 'Pause' }).click()
})

test('a layer whose tiles fail shows a warning and can be retried', async ({ page }) => {
  await mockBasemap(page)
  await page.goto('/')
  await page.getByRole('navigation', { name: 'Sections' }).waitFor()
  await switchOn(page, 'Alpha section', 'Fake yearly')
  const active = page.getByRole('region', { name: 'Active layers' })
  await expect(active.getByText('Could not load')).toBeVisible()

  await page.route('**/api/tiles/**', (route) => route.fulfill({ status: 200, contentType: 'image/png', body: '' }))
  await active.getByRole('button', { name: 'Retry Fake yearly' }).click()
  await expect(active.getByText('Could not load')).toHaveCount(0)
})
