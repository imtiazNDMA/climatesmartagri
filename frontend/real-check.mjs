import { chromium } from '@playwright/test'
const [out, layer, name] = process.argv.slice(2)
const browser = await chromium.launch()
const page = await browser.newPage({ viewport: { width: 1600, height: 950 } })
const times = []
page.on('requestfinished', (r) => { if (r.url().includes('/api/cog/')) times.push(Math.round(r.timing().responseEnd)) })
await page.goto(`http://127.0.0.1:9080/?section=land-cover&layers=${layer}:0.9`)
await page.locator('[data-boundaries-drawn="true"]').waitFor({ timeout: 40000 })
await page.waitForTimeout(6000)
times.sort((a, b) => a - b)
console.log(layer, 'could not load:', await page.getByText('Could not load').count(), '| tiles:', times.length, 'median ms:', times[Math.floor(times.length / 2)], 'max ms:', times[times.length - 1])
await page.screenshot({ path: `${out}/${name}.png` })
await browser.close()
