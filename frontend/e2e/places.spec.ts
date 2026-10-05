import { expect, test } from '@playwright/test'
import { openPortal } from './helpers'

test('select a province, then a district, then step back with the breadcrumb', async ({ page }) => {
  await openPortal(page)
  const crumbs = page.getByRole('navigation', { name: 'Selected place' })
  const search = page.getByRole('searchbox', { name: 'Search place' })
  await expect(crumbs.getByRole('listitem')).toHaveText(['Pakistan'])

  await search.fill('alp')
  await page.getByRole('option', { name: /Alpha/ }).click()
  await expect(crumbs.getByRole('listitem')).toHaveText(['Pakistan', 'Alpha'])
  await expect(search).toHaveValue('')

  await search.fill('district one')
  await page.getByRole('option', { name: /District One/ }).click()
  await expect(crumbs.getByRole('listitem')).toHaveText(['Pakistan', 'Alpha', 'District One'])

  await crumbs.getByRole('button', { name: 'Alpha' }).click()
  await expect(crumbs.getByRole('listitem')).toHaveText(['Pakistan', 'Alpha'])
  await crumbs.getByRole('button', { name: 'Pakistan' }).click()
  await expect(crumbs.getByRole('listitem')).toHaveText(['Pakistan'])
})

test('search ignores case and spaces, names the level, and says when nothing matches', async ({ page }) => {
  await openPortal(page)
  const search = page.getByRole('searchbox', { name: 'Search place' })
  await search.fill('  DISTRICT T ')
  await expect(page.getByRole('option')).toHaveText([/District Three.*District in Beta/, /District Two.*District in Alpha/])
  await search.fill('zzz')
  await expect(page.getByText('No places match')).toBeVisible()
  await search.fill('')
  await expect(page.getByRole('option')).toHaveCount(0)
})

test('the figures heading follows the selected place', async ({ page }) => {
  await openPortal(page)
  await page.getByRole('button', { name: 'Alpha section' }).click()
  await expect(page.getByRole('heading', { name: 'Figures for Pakistan' })).toBeVisible()
  await page.getByRole('searchbox', { name: 'Search place' }).fill('beta')
  await page.getByRole('option', { name: /Beta/ }).click()
  await expect(page.getByRole('heading', { name: 'Figures for Beta' })).toBeVisible()
})

test('the figures say which place they are for and offer the way back to the whole country', async ({ page }) => {
  await openPortal(page, '/?section=alpha-section&place=PK101')
  const panel = page.locator('.panel')
  await expect(panel.getByRole('heading', { name: 'Figures for District One' })).toBeVisible()
  await panel.getByRole('button', { name: 'Show all of Pakistan' }).click()
  await expect(panel.getByRole('heading', { name: 'Figures for Pakistan' })).toBeVisible()
  await expect(page).not.toHaveURL(/place=/)
  await expect(panel.getByRole('button', { name: 'Show all of Pakistan' })).toHaveCount(0)
})

test('the full view offers the way back to the whole country too', async ({ page }) => {
  await openPortal(page, '/?section=alpha-section&view=charts&place=PK1')
  const full = page.getByRole('region', { name: 'Charts in full view' })
  await expect(full.getByText('Alpha', { exact: true })).toBeVisible()
  await full.getByRole('button', { name: 'Show all of Pakistan' }).click()
  await expect(full.getByText('Pakistan', { exact: true })).toBeVisible()
  await expect(page).not.toHaveURL(/place=/)
})
