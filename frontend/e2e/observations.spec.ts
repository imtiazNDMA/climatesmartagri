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
