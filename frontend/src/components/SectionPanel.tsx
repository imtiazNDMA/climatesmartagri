import { X } from 'lucide-react'
import { useState, type PointerEvent as ReactPointerEvent } from 'react'
import { COUNTRY_ID } from '../api/types'
import type { PortalData } from '../data/usePortalData'
import { useSectionData, type SectionDataState } from '../data/useSectionData'
import { effectiveYear } from '../state/selectors'
import { useView, viewStore } from '../state/viewState'

const MIN_WIDTH = 280
const MAX_WIDTH = 640

function Figures({ state, placeSelected }: { state: SectionDataState; placeSelected: boolean }) {
  if (state.status === 'no-data') return <p className="empty">Data not loaded yet</p>
  if (state.status === 'loading' || state.status === 'idle') return <p className="empty">Loading…</p>
  if (state.status === 'error') return <p className="empty">Figures could not be loaded: {state.message}</p>
  if (state.status === 'coming-soon') return null
  const { data } = state
  return (
    <>
      {placeSelected && data.level_used === 'national' && <p className="national-only">National figures only</p>}
      {data.figures.length === 0 ? (
        <p className="empty">No figures for this section yet.</p>
      ) : (
        <dl className="figures">
          {data.figures.map((figure) => (
            <div key={figure.label}>
              <dt>{figure.label}</dt>
              <dd>{[figure.value, figure.unit].filter((part) => part !== '').join(' ')}</dd>
            </div>
          ))}
        </dl>
      )}
    </>
  )
}

export function SectionPanel({ data }: { data: PortalData }) {
  const sectionId = useView((s) => s.section)
  const activeLayers = useView((s) => s.layers)
  const placeId = useView((s) => s.place)
  const year = useView((s) => s.year)
  const [width, setWidth] = useState(340)

  const section = data.catalogue.sections.find((s) => s.id === sectionId) ?? null
  const sectionData = useSectionData(section, placeId, effectiveYear(section?.years, year))
  if (!section) return null

  const place = data.places.find((p) => p.id === (placeId ?? COUNTRY_ID))
  const layers = data.catalogue.layers.filter((l) => l.section_id === section.id && l.kind !== 'boundary')

  const startResize = (event: ReactPointerEvent) => {
    const startX = event.clientX
    const startWidth = width
    const move = (e: PointerEvent) =>
      setWidth(Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, startWidth + e.clientX - startX)))
    const stop = () => {
      window.removeEventListener('pointermove', move)
      window.removeEventListener('pointerup', stop)
    }
    window.addEventListener('pointermove', move)
    window.addEventListener('pointerup', stop)
  }

  return (
    <aside className="panel" style={{ width }} aria-label={section.title}>
      <header className="panel-header">
        <h2>{section.title}</h2>
        <button type="button" aria-label="Close panel" onClick={() => viewStore.getState().closeSection()}>
          <X size={18} />
        </button>
      </header>

      {section.status === 'coming-soon' ? (
        <div className="panel-body">
          <p className="coming-soon">Coming soon</p>
          <p>{section.summary}</p>
        </div>
      ) : (
        <div className="panel-body">
          <section>
            <h3>Layers</h3>
            {layers.length === 0 && (
              <p className="empty">
                {section.status === 'no-data' ? 'Data not loaded yet' : 'This section has no map layers.'}
              </p>
            )}
            {layers.map((layer) => {
              const ready = layer.status === 'ready'
              return (
                <label key={layer.id} className={`layer-switch${ready ? '' : ' disabled'}`}>
                  <input
                    type="checkbox"
                    role="switch"
                    aria-label={layer.title}
                    disabled={!ready}
                    checked={activeLayers.some((l) => l.id === layer.id)}
                    onChange={() => viewStore.getState().toggleLayer(layer.id, layer.default_opacity)}
                  />
                  <span>{layer.title}</span>
                  {!ready && <small>Data not loaded yet</small>}
                </label>
              )
            })}
          </section>
          <section>
            <h3>Figures for {place?.name ?? 'Pakistan'}</h3>
            <Figures state={sectionData} placeSelected={placeId !== null} />
          </section>
          <section>
            <h3>Charts</h3>
            <p className="empty">
              {sectionData.status === 'ready' ? 'No charts for this section yet.' : 'Data not loaded yet'}
            </p>
          </section>
        </div>
      )}
      <div className="panel-resize" onPointerDown={startResize} role="separator" aria-orientation="vertical" />
    </aside>
  )
}
