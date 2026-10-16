import { expect, test } from '@playwright/test'

const TOKEN = 'e2e-ops-token'

test('the dashboard asks for its token and says when it is wrong', async ({ page }) => {
  await page.goto('/ops')
  await expect(page.getByRole('heading', { name: 'AI Ops' })).toBeVisible()

  await page.getByLabel('Ops token').fill('wrong')
  await page.getByRole('button', { name: 'Open dashboard' }).click()
  await expect(page.getByRole('alert')).toHaveText('That token was not accepted.')

  await page.getByLabel('Ops token').fill(TOKEN)
  await page.getByRole('button', { name: 'Open dashboard' }).click()
  await expect(page.getByRole('navigation', { name: 'AI Ops views' })).toBeVisible()
  expect(await page.evaluate(() => sessionStorage.getItem('csa-ops-token'))).toBe(TOKEN)
})

test('a token the server stops accepting brings the form back', async ({ page }) => {
  await page.addInitScript(() => sessionStorage.setItem('csa-ops-token', 'rotated-away'))
  await page.goto('/ops')

  await expect(page.getByRole('alert')).toHaveText('That token was not accepted.')
  await expect(page.getByLabel('Ops token')).toBeVisible()
})

test('the portal itself is unchanged', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'AI Ops' })).toHaveCount(0)
})

test.describe('with the token', () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript((token) => sessionStorage.setItem('csa-ops-token', token), TOKEN)
  })

  test('the overview states the evaluation and traffic findings', async ({ page }) => {
    await page.goto('/ops')

    await expect(page.getByRole('heading', { name: 'Golden pass rate fell 16.7 points to 50.0%' })).toBeVisible()
    const golden = page.getByRole('group', { name: 'Golden pass^k' })
    await expect(golden).toContainText('50.0%')
    await expect(golden).toContainText('−16.7 pts')
    await expect(page.getByRole('group', { name: 'Judge faithfulness (uncalibrated)' })).toContainText('66.7%')
    await expect(page.getByRole('heading', { name: '4 questions in the last 24 hours, 25.0% failed' })).toBeVisible()
    await expect(page.getByRole('img', { name: 'Pass rate over time' })).toBeVisible()

    await page.getByRole('radio', { name: '7 days' }).check()
    await expect(page.getByRole('heading', { name: '6 questions in the last 7 days, 33.3% failed' })).toBeVisible()
    await expect(page.getByRole('row', { name: /get_section_facts/ })).toContainText('3')
  })

  test('two runs of a dataset can be compared, and a run shows its cases by repeat', async ({ page }) => {
    await page.goto('/ops#/runs')

    const rows = page.getByRole('row').filter({ hasText: 'golden' })
    await expect(rows).toHaveCount(3)
    await page.getByRole('checkbox', { name: 'Select golden run aaa1111' }).check()
    await page.getByRole('checkbox', { name: 'Select golden run bbb2222 (live)' }).check()
    await page.getByRole('button', { name: 'Compare selected' }).click()

    await expect(page.getByRole('heading', { name: '1 regression and 1 fix from aaa1111 to bbb2222' })).toBeVisible()
    await expect(page.getByRole('list', { name: 'Regressions' })).toContainText('case-b')
    await expect(page.getByRole('list', { name: 'New cases' })).toContainText('case-d')

    await page.goto('/ops#/runs')
    await page.getByRole('link', { name: 'golden bbb2222 (live)' }).click()
    await expect(page.getByRole('heading', { name: /golden: 2 of 4 cases passed every repeat/ })).toBeVisible()
    await expect(page.getByRole('cell', { name: 'case-b repeat 1: failed' })).toBeVisible()
    await expect(page.getByRole('row', { name: /case-b/ })).toContainText('required_terms: missing: Punjab')
  })

  test('traces filter, page, and open as a span waterfall', async ({ page }) => {
    await page.goto('/ops#/traces')

    await expect(page.getByRole('heading', { name: '10 traces shown' })).toBeVisible()
    await page.getByLabel('Source').selectOption('live')
    await expect(page.getByRole('heading', { name: '6 traces shown' })).toBeVisible()
    await page.getByLabel('Status').selectOption('error')
    await expect(page.getByRole('row', { name: /tool-limit/ })).toBeVisible()
    await page.getByLabel('Status').selectOption('')

    await page.getByRole('link', { name: /^Open trace/ }).first().click()
    const bars = page.getByTestId('waterfall').locator('[data-span]')
    await expect(bars).toHaveCount(4)
    await expect(bars.first()).toHaveAttribute('aria-label', /agent assistant, 7\.99 s/)
    await expect(page.getByText('Question text not kept for live traces')).toBeVisible()
  })

  test('answers are labelled by keyboard, and typing a note does not change the label', async ({ page }) => {
    await page.goto('/ops#/labels')

    const before = await page.getByRole('group', { name: 'Judge gemma' }).textContent()
    await expect(page.getByText('Answer for case-b')).toBeVisible()
    await page.getByLabel('Your name').fill('E2E officer')
    // Clicking the answer's text moves the focus out of the inputs, so the keys are shortcuts again.
    await page.getByText('Answer for case-b').click()
    await page.keyboard.press('n')
    await page.keyboard.press('2')
    await page.getByLabel('Note').fill('yes 5 n')
    await expect(page.getByRole('radio', { name: 'Not faithful' })).toBeChecked()
    await expect(page.getByRole('radio', { name: '2' })).toBeChecked()
    await page.getByRole('button', { name: 'Save label' }).click()

    await expect(page.getByText('Answer for case-c')).toBeVisible()
    await expect(page.getByRole('group', { name: 'Judge gemma' })).not.toHaveText(before ?? '')
  })
})
