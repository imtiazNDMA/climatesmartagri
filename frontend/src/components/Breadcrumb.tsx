import { useMemo } from 'react'
import type { Place } from '../api/types'
import { ancestors } from '../state/selectors'
import { useView, viewStore } from '../state/viewState'

export function Breadcrumb({ places }: { places: Place[] }) {
  const placeId = useView((s) => s.place)
  const trail = useMemo(() => ancestors(places, placeId), [places, placeId])

  return (
    <nav className="breadcrumb" aria-label="Selected place">
      <ol>
        {trail.map((place, index) => {
          const isCurrent = index === trail.length - 1
          return (
            <li key={place.id}>
              {isCurrent ? (
                <span aria-current="location">{place.name}</span>
              ) : (
                <button type="button" onClick={() => viewStore.getState().selectPlace(place.id)}>
                  {place.name}
                </button>
              )}
            </li>
          )
        })}
      </ol>
    </nav>
  )
}
