import { useSyncExternalStore } from 'react'

/** Whether the page is in its dark theme, as App marks it on the root element. Updates when it changes. */
export function useDarkTheme(): boolean {
  return useSyncExternalStore(subscribe, isDark, () => false)
}

const isDark = () => document.documentElement.dataset.theme === 'dark'

function subscribe(onChange: () => void): () => void {
  const observer = new MutationObserver(onChange)
  observer.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] })
  return () => observer.disconnect()
}
