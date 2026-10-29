/**
 * Opens the portal in the browser once it answers end to end. The frontend is ready within a second
 * but the backend takes longer to load its data, so opening the browser as soon as the frontend is up
 * showed a page whose first requests had all failed.
 *
 * Usage: node scripts/open-when-ready.mjs [url]
 */
import { spawn } from 'node:child_process'
import { pathToFileURL } from 'node:url'

/** Waits until `check` says the portal answers, then opens it. Resolves whether it was opened. */
export async function openWhenReady({ check, open, wait, url, attempts }) {
  for (let attempt = 0; attempt < attempts; attempt++) {
    const ready = await check().catch(() => false)
    if (ready) {
      open(url)
      return true
    }
    await wait()
  }
  return false
}

function openInBrowser(url) {
  const [command, args] =
    process.platform === 'win32' ? ['cmd', ['/c', 'start', '""', url]]
    : process.platform === 'darwin' ? ['open', [url]]
    : ['xdg-open', [url]]
  spawn(command, args, { stdio: 'ignore', detached: true, windowsVerbatimArguments: true }).unref()
}

if (import.meta.url === pathToFileURL(process.argv[1]).href) {
  const url = process.argv[2] ?? 'http://127.0.0.1:9080'
  // Through the frontend, so it answers only when the frontend and the backend behind it are both up.
  const health = `${url}/api/health`
  const ready = await openWhenReady({
    check: async () => (await fetch(health, { signal: AbortSignal.timeout(5000) })).ok,
    open: openInBrowser,
    wait: () => new Promise((resolve) => setTimeout(resolve, 1000)),
    url,
    attempts: 300,
  })
  console.log(ready ? `Opened ${url}` : `The portal did not answer at ${health}; open ${url} once it does.`)
  // Stay running: the launcher stops the whole portal as soon as any one of its processes ends.
  setInterval(() => {}, 1 << 30)
}
