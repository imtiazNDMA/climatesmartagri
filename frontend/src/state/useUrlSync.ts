import { useEffect } from 'react'
import type { Catalogue, Place } from '../api/types'
import { tidyYear } from './selectors'
import { uiStore } from './uiState'
import { parseView, serializeView } from './urlState'
import { pickView, viewStore } from './viewState'

/** Read the view from the address bar once the data has loaded, then keep the address bar in step. */
export function useUrlSync(catalogue: Catalogue, places: Place[]): void {
  useEffect(() => {
    const { view, dropped } = parseView(window.location.search, catalogue, places)
    viewStore.getState().replaceView(view)
    if (dropped.length) {
      uiStore.getState().addNotice(`Ignored from the link: ${dropped.join(', ')}.`)
    }
    const write = () => {
      const state = viewStore.getState()
      const year = tidyYear(pickView(state), catalogue)
      if (year !== state.year) {
        // Setting the year calls this again, which then writes the address bar.
        state.setYear(year)
        return
      }
      const query = serializeView(pickView(state))
      window.history.replaceState(null, '', `${window.location.pathname}${query}`)
    }
    write()
    return viewStore.subscribe(write)
  }, [catalogue, places])
}
