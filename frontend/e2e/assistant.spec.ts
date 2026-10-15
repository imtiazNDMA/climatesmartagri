import { expect, test } from '@playwright/test'
import { openPortal } from './helpers'

test('the local AI guide provides an overview, tour and grounded chat', async ({ page }) => {
  await page.route('**/api/assistant/chat', async (route) => {
    const request = route.request().postDataJSON()
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        answer: `This answer is grounded in ${request.view.section_id ?? 'the portal overview'}.`,
        sources: ['Portal catalogue'],
        model: 'qwen',
      }),
    })
  })
  await openPortal(page)

  await page.getByRole('button', { name: 'AI portal guide' }).click()
  const guide = page.getByRole('dialog', { name: 'Portal AI assistant' })
  await expect(guide).toBeVisible()
  await expect(guide.getByText('Explore the portal')).toBeVisible()

  await guide.getByRole('button', { name: 'Tour', exact: true }).click()
  await expect(guide.getByText('Story 1 of')).toBeVisible()
  await guide.getByRole('button', { name: 'Ask' }).click()
  await guide.getByRole('textbox', { name: 'Question for the portal guide' }).fill('What is this portal?')
  await guide.getByRole('button', { name: 'Send question' }).click()
  await expect(guide.getByText('This answer is grounded in the portal overview.')).toBeVisible()
})
