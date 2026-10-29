import { expect, test } from '@playwright/test'
import { openPortal } from './helpers'

test('the local AI guide provides an overview, tour and grounded chat', async ({ page }) => {
  await page.route('**/api/assistant/chat', async (route) => {
    const request = route.request().postDataJSON()
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        answer: `This answer is grounded in ${request.view.section_id ?? 'the portal overview'}.`,
        sources: ['fact:0123456789ab'],
        source_names: ['Alpha section / Pakistan'],
        model: 'qwen',
        grounded: false,
        unchecked_numbers: [999],
        tool_calls: 1,
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
  await guide.getByRole('button', { name: 'Ask', exact: true }).click()
  await guide.getByRole('textbox', { name: 'Question for the portal guide' }).fill('What is this portal?')
  await guide.getByRole('button', { name: 'Send question' }).click()
  await expect(guide.getByText('This answer is grounded in the portal overview.')).toBeVisible()
  await expect(guide.getByText('Sources: Alpha section / Pakistan')).toBeVisible()
  await expect(guide.getByText('fact:0123456789ab')).toHaveCount(0)
  await expect(guide.getByRole('status').filter({ hasText: 'Unchecked: 999.' })).toBeVisible()
})

test('the portal tour advances automatically and still supports manual next', async ({ page }) => {
  await page.clock.install()
  await openPortal(page)
  await page.getByRole('button', { name: 'AI portal guide' }).click()
  const guide = page.getByRole('dialog', { name: 'Portal AI assistant' })

  await guide.getByRole('button', { name: 'Tour', exact: true }).click()
  await expect(guide.getByText('Story 1 of')).toBeVisible()
  await page.clock.fastForward(7000)
  await expect(guide.getByText('Story 2 of')).toBeVisible()

  await guide.getByRole('button', { name: 'Next' }).click()
  await expect(guide.getByText('Story 3 of')).toBeVisible()
})

test('assistant markdown is formatted instead of displayed as source text', async ({ page }) => {
  await page.route('**/api/assistant/chat', async (route) => route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify({
      answer: '## Available information\n\nThe portal covers **agriculture and climate**.\n\n| Section | Status |\n|---|---|\n| Land Classification | Ready |',
      sources: [], source_names: [], model: 'qwen', grounded: true, unchecked_numbers: [], tool_calls: 0,
    }),
  }))
  await openPortal(page)
  await page.getByRole('button', { name: 'AI portal guide' }).click()
  const guide = page.getByRole('dialog', { name: 'Portal AI assistant' })
  await guide.getByRole('button', { name: 'Ask', exact: true }).click()
  await guide.getByRole('textbox', { name: 'Question for the portal guide' }).fill('What is available?')
  await guide.getByRole('button', { name: 'Send question' }).click()

  await expect(guide.getByRole('heading', { name: 'Available information' })).toBeVisible()
  await expect(guide.getByRole('table')).toBeVisible()
  await expect(guide.getByText('**agriculture and climate**')).toHaveCount(0)
})

test('the launcher and open guide can be dragged without leaving the viewport', async ({ page }) => {
  await openPortal(page)
  const launcher = page.getByRole('button', { name: 'AI portal guide' })
  const before = await launcher.boundingBox()
  if (!before) throw new Error('launcher has no bounds')

  await launcher.hover()
  await page.mouse.down()
  await page.mouse.move(before.x - 180, before.y - 120, { steps: 4 })
  await page.mouse.up()
  const moved = await launcher.boundingBox()
  if (!moved) throw new Error('moved launcher has no bounds')
  expect(moved.x).toBeLessThan(before.x - 100)
  await expect(page.getByRole('dialog', { name: 'Portal AI assistant' })).toHaveCount(0)

  await launcher.click()
  const guide = page.getByRole('dialog', { name: 'Portal AI assistant' })
  const header = guide.getByLabel('Drag portal guide')
  const panelBefore = await guide.boundingBox()
  if (!panelBefore) throw new Error('guide has no bounds')
  await header.hover()
  await page.mouse.down()
  await page.mouse.move(panelBefore.x + 120, panelBefore.y + 150, { steps: 4 })
  await page.mouse.up()
  await page.waitForTimeout(50)
  const panelAfter = await guide.boundingBox()
  if (!panelAfter) throw new Error('dragged guide has no bounds')
  expect(panelAfter.x).toBeGreaterThanOrEqual(8)
  expect(panelAfter.y).toBeGreaterThanOrEqual(8)
  const viewport = page.viewportSize()
  if (!viewport) throw new Error('page has no viewport')
  expect(panelAfter.x + panelAfter.width).toBeLessThanOrEqual(viewport.width)
  expect(panelAfter.y + panelAfter.height).toBeLessThanOrEqual(viewport.height)
})

test('the guide animates out before restoring the launcher', async ({ page }) => {
  // A fake clock, so a slow machine cannot run the 160 ms close animation out before it is checked.
  await page.clock.install()
  await openPortal(page)
  await page.getByRole('button', { name: 'AI portal guide' }).click()
  const guide = page.getByRole('dialog', { name: 'Portal AI assistant' })
  await expect(guide).toBeVisible()

  await page.clock.pauseAt(Date.now() + 60_000)
  await guide.getByRole('button', { name: 'Close assistant' }).click()
  await expect(guide).toHaveClass(/assistant-closing/)
  await expect(guide).toHaveCount(1)
  await page.clock.runFor(200)
  await expect(guide).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'AI portal guide' })).toBeVisible()
})

test('the launcher animation loads its player from the portal, not a CDN', async ({ page }) => {
  const external: string[] = []
  page.on('request', (request) => {
    if (/unpkg\.com|jsdelivr\.net/.test(request.url())) external.push(request.url())
  })
  const wasm = page.waitForResponse((response) => /dotlottie-player.*\.wasm/.test(response.url()))
  await openPortal(page)

  const response = await wasm
  expect(new URL(response.url()).host).toBe(new URL(page.url()).host)
  expect(response.status()).toBe(200)
  await page.waitForTimeout(500)
  expect(external).toEqual([])
})
