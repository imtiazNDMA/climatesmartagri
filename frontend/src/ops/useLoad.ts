import { useCallback, useEffect, useState } from 'react'

export interface Loaded<T> { state: 'loading' | 'ready' | 'error'; data?: T; error?: Error; reload: () => void }

/** Runs `load` whenever `deps` change; an answer that arrives after a newer request has started is dropped. */
export function useLoad<T>(load: () => Promise<T>, deps: unknown[]): Loaded<T> {
  const [version, setVersion] = useState(0)
  const [result, setResult] = useState<Omit<Loaded<T>, 'reload'>>({ state: 'loading' })
  const reload = useCallback(() => setVersion((v) => v + 1), [])
  useEffect(() => {
    let current = true
    setResult((previous) => ({ ...previous, state: 'loading' }))
    load().then(
      (data) => current && setResult({ state: 'ready', data }),
      (error: unknown) => current && setResult({ state: 'error', error: error instanceof Error ? error : new Error(String(error)) }),
    )
    return () => {
      current = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, version])
  return { ...result, reload }
}
