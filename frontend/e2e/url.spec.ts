import { expect, test } from '@playwright/test'
import { openPortal } from './helpers'

test('reloading the page restores the same view', async ({ page }) => {
  await openPortal(page)
  await page.getByRole('button', { name: 'Beta section' }).click()
  await page.getByRole('switch', { name: 'Fake static' }).check()
  await page.getByRole('button', { name: 'Alpha section' }).click()
  await page.getByRole('switch', { name: 'Fake yearly' }).check()
  const active = page.getByRole('region', { name: 'Active layers' })
  await active.getByRole('button', { name: 'Hide Fake static' }).click()
  await page.getByRole('searchbox', { name: 'Search place' }).fill('district one')
  await page.getByRole('option', { name: /District One/ }).click()
  await page.getByRole('group', { name: 'Year' }).getByRole('button', { name: 'Previous year' }).click()

  await expect(page).toHaveURL(
    /\?section=alpha-section&layers=fake-yearly:0\.8,fake-static:1&hidden=fake-static&place=PK101&year=2009$/,
  )
  await page.reload()

  await expect(page.getByRole('heading', { name: 'Alpha section' })).toBeVisible()
  await expect(active.getByRole('listitem')).toHaveText([/Fake yearly/, /Fake static/])
  await expect(active.getByRole('button', { name: 'Show Fake static' })).toBeVisible()
  await expect(page.getByRole('navigation', { name: 'Selected place' }).getByRole('listitem')).toHaveText([
    'Pakistan', 'Alpha', 'District One',
  ])
  await expect(page.getByRole('group', { name: 'Year' }).getByRole('slider')).toHaveValue('2009')
})

test('a plain address stays plain', async ({ page }) => {
  await openPortal(page)
  await expect(page).toHaveURL(/127\.0\.0\.1:5183\/$/)
})

test('invalid values in a link are dropped with a notice and the rest loads', async ({ page }) => {
  await openPortal(page, '/?section=alpha-section&layers=ghost:1,fake-static:9&place=XX&year=1800')
  await expect(page.getByRole('heading', { name: 'Alpha section' })).toBeVisible()
  await expect(page.getByRole('region', { name: 'Active layers' }).getByRole('listitem')).toHaveText([/Fake static/])
  const notice = page.getByText(/Ignored from the link/)
  await expect(notice).toContainText('layer "ghost"')
  await expect(notice).toContainText('opacity "9" for layer "fake-static"')
  await expect(notice).toContainText('place "XX"')
  await expect(notice).toContainText('year "1800"')
  await expect(page).toHaveURL(/\?section=alpha-section&layers=fake-static:1$/)
})
