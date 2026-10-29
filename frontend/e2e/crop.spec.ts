import { expect, test, type Page } from '@playwright/test'
import { openPortal } from './helpers'

const LEAF = {
  name: 'leaf.png',
  mimeType: 'image/png',
  buffer: Buffer.from(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==',
    'base64',
  ),
}

const GUIDANCE = {
  name: 'Whitefly infestation',
  type: 'Pest',
  symptoms: ['Small white flying insects that scatter when plants are disturbed'],
  prevention: ['Remove weed hosts and volunteer cotton between seasons.'],
  treatment_steps: [],
  reviewed: false,
  version: 'draft-2026-10',
  source: 'test guide',
}

/** The fixture catalogue has no detector section; add the real one, and answer predictions without a model. */
async function openDetector(page: Page, needsReview: boolean) {
  await page.route('**/api/catalogue', async (route) => {
    const catalogue = await (await route.fetch()).json()
    catalogue.sections.push({
      id: 'crop-classification', title: 'AI Crop Disease and Pest Detector', icon: 'scan-search', order: 8,
      status: 'ready', kind: 'crop-classification', summary: 'Five crops.', place_levels: ['national'],
    })
    await route.fulfill({ json: catalogue })
  })
  const requests: string[] = []
  await page.route('**/api/crop-classification/predict', async (route) => {
    requests.push(route.request().postData() ?? '')
    await route.fulfill({
      json: {
        predictions: [
          { label_index: 8, canonical_class_id: 'cotton_whitefly', canonical_class: 'Whitefly (cotton)', crop: 'Cotton', category: 'pest', confidence: needsReview ? 0.41 : 0.98 },
          { label_index: 2, canonical_class_id: 'cotton_aphid', canonical_class: 'Aphid (cotton)', crop: 'Cotton', category: 'pest', confidence: 0.02 },
        ],
        needs_expert_review: needsReview,
        model: 'five-crop-001',
        calibrated: true,
        guidance: GUIDANCE,
      },
    })
  })
  await openPortal(page)
  await page.getByRole('button', { name: 'AI Crop Disease and Pest Detector' }).click()
  await page.getByRole('button', { name: 'Cotton', exact: true }).click()
  await page.locator('.crop-file-input').setInputFiles(LEAF)
  await page.getByRole('button', { name: 'Classify crop image' }).click()
  return requests
}

test('a cotton leaf comes back with its class, what to look for and prevention, but no treatment steps', async ({ page }) => {
  const requests = await openDetector(page, false)

  await expect(page.getByRole('heading', { name: 'Whitefly (cotton)' })).toBeVisible()
  expect(requests[0]).toContain('Cotton')
  const guidance = page.getByRole('region', { name: 'Guidance' })
  await expect(guidance.getByRole('heading', { name: 'Whitefly infestation' })).toBeVisible()
  await expect(guidance.getByText('Small white flying insects')).toBeVisible()
  await expect(guidance.getByText('Remove weed hosts')).toBeVisible()
  await expect(guidance.getByRole('heading', { name: 'What to do' })).toHaveCount(0)
  await expect(guidance.getByText('Treatment steps are held back')).toBeVisible()
  await expect(page.getByText('not calibrated yet')).toHaveCount(0)
})

test('an uncertain result leads with the review message and offers guidance only as a possibility', async ({ page }) => {
  await openDetector(page, true)

  const review = page.getByText('The result is uncertain')
  await expect(review).toBeVisible()
  const reviewTop = (await review.boundingBox())!.y
  const resultTop = (await page.getByRole('heading', { name: 'Whitefly (cotton)' }).boundingBox())!.y
  expect(reviewTop).toBeLessThan(resultTop)
  await expect(page.getByRole('heading', { name: 'If it is whitefly infestation' })).toBeVisible()
})
