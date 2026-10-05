import { Search } from 'lucide-react'
import { useMemo, useState } from 'react'
import type { Place } from '../api/types'
import { searchPlaces } from '../state/selectors'
import { viewStore } from '../state/viewState'

export function PlaceSearch({ places }: { places: Place[] }) {
  const [query, setQuery] = useState('')
  const results = useMemo(() => searchPlaces(places, query), [places, query])
  const names = useMemo(() => new Map(places.map((p) => [p.id, p.name])), [places])

  const choose = (place: Place) => {
    viewStore.getState().selectPlace(place.id)
    setQuery('')
  }
  const describe = (place: Place) =>
    place.level === 'province' ? 'Province' : `District in ${names.get(place.parent_id ?? '') ?? 'Pakistan'}`

  return (
    <div className="place-search">
      <Search size={16} aria-hidden />
      <input
        type="search"
        aria-label="Search place"
        placeholder="Search place…"
        value={query}
        onChange={(event) => setQuery(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === 'Enter' && results[0]) choose(results[0])
          if (event.key === 'Escape') setQuery('')
        }}
      />
      {query.trim() !== '' && (
        <ul className="place-results" role="listbox" aria-label="Matching places">
          {results.map((place) => (
            <li key={place.id} role="option" aria-selected={false} onClick={() => choose(place)}>
              <strong>{place.name}</strong>
              <small>{describe(place)}</small>
            </li>
          ))}
          {results.length === 0 && <li className="empty">No places match</li>}
        </ul>
      )}
    </div>
  )
}
