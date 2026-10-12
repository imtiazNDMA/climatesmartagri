import { BarChart3, Hash, Layers, Maximize2, X, type LucideIcon } from 'lucide-react'
import { useState, type PointerEvent as ReactPointerEvent, type ReactNode } from 'react'
import { COUNTRY_ID, type Figure, type Layer } from '../api/types'
import { formatNumber } from '../charts/chartOption'
import type { ForecastTimesState } from '../data/useForecastTimes'
import type { PortalData } from '../data/usePortalData'
import type { SectionDataState } from '../data/useSectionData'
import { useView, viewStore } from '../state/viewState'
import { ChartFigure } from './ChartFigure'
import { ForecastPanel } from './ForecastPanel'
import { figureBar, groupLayers, layerScope, layerSwatch } from './panelParts'
import { sectionIcon } from './sectionIcons'

const MIN_WIDTH = 280
const MAX_WIDTH = 760

/** A part of the panel under its own heading: a small picture, the heading, and a count when there is one. */
function Part({ icon: Icon, heading, count, action, children }: {
  icon: LucideIcon
  heading: ReactNode
  count?: string
  action?: ReactNode
  children: ReactNode
}) {
  return (
    <section className="panel-part">
      <div className="part-head">
        <Icon size={19} aria-hidden />
        <h3>{heading}</h3>
        {count && <span className="part-count">{count}</span>}
        {action}
      </div>
      {children}
    </section>
  )
}

/** One figure as a tile: what it is, the number large with its unit small, and a bar when it is a share. */
function FigureTile({ figure }: { figure: Figure }) {
  const bar = figureBar(figure)
  const share = typeof figure.share === 'number' ? figure.share : null
  return (
    <div className="figure-tile">
      <dt>{figure.label}</dt>
      <dd>
        {figure.value === null ? (
          'Not reported'
        ) : (
          <>
            <span className="figure-number">{formatNumber(figure.value)}</span>
            {figure.unit !== '' && (
              <>
                {' '}
                <span className="figure-unit">{figure.unit}</span>
              </>
            )}
          </>
        )}
      </dd>
      {bar !== null && figure.value !== null && (
        <div className="figure-share">
          <span className="figure-bar" aria-hidden>
            <span style={{ width: `${bar}%` }} />
          </span>
          {share !== null && (
            <span className="figure-share-text">
              {formatNumber(share)}%{figure.share_of ? ` ${figure.share_of}` : ''}
            </span>
          )}
        </div>
      )}
    </div>
  )
}

function Figures({ state, placeSelected }: { state: SectionDataState; placeSelected: boolean }) {
  if (state.status === 'no-data') return <p className="empty">Data not loaded yet</p>
  if (state.status === 'loading' || state.status === 'idle') return <p className="empty">Loading…</p>
  if (state.status === 'error') return <p className="empty">Figures could not be loaded: {state.message}</p>
  if (state.status === 'coming-soon') return null
  const { data } = state
  return (
    <>
      {placeSelected && data.level_used === 'national' && <p className="national-only">National figures only</p>}
      {data.figures.length > 0 && (
        // Keyed by place and year, so the tiles fade in afresh when the figures are for somewhere else.
        <dl className="figures" key={`${data.place_id}-${data.year}`}>
          {data.figures.map((figure) => (
            <FigureTile key={figure.label} figure={figure} />
          ))}
        </dl>
      )}
      {(data.notes ?? []).map((note) => (
        <p className="note" key={note}>
          {note}
        </p>
      ))}
      {data.figures.length === 0 && (data.notes ?? []).length === 0 && (
        <p className="empty">No figures for this selection.</p>
      )}
    </>
  )
}

/** A layer as a row: a strip of its colours, its name, and the switch that puts it on the map. */
function LayerRow({ layer, on }: { layer: Layer; on: boolean }) {
  const ready = layer.status === 'ready'
  return (
    <label className={`layer-switch${on ? ' on' : ''}${ready ? '' : ' disabled'}`}>
      <span className="layer-swatch" style={{ background: layerSwatch(layer) }} aria-hidden />
      <span className="layer-name">
        {layerScope(layer.title).name}
        {!ready && <small>Data not loaded yet</small>}
      </span>
      <input
        type="checkbox"
        role="switch"
        aria-label={layer.title}
        disabled={!ready}
        checked={on}
        onChange={() => viewStore.getState().toggleLayer(layer.id, layer.default_opacity)}
      />
    </label>
  )
}

export function SectionPanel({ data, sectionData, forecastTimes }: {
  data: PortalData
  sectionData: SectionDataState
  forecastTimes: ForecastTimesState
}) {
  const sectionId = useView((s) => s.section)
  const full = useView((s) => s.full)
  const activeLayers = useView((s) => s.layers)
  const placeId = useView((s) => s.place)
  const [width, setWidth] = useState(480)

  const section = data.catalogue.sections.find((s) => s.id === sectionId) ?? null
  if (!section) return null
  const hasCharts = sectionData.status === 'ready' && sectionData.data.charts.length > 0
  // The place the figures are actually for, when the section has none for the selected one.
  const usedPlace =
    sectionData.status === 'ready' && placeId !== null && sectionData.data.place_id !== placeId
      ? data.places.find((p) => p.id === sectionData.data.place_id)
      : undefined

  const place = data.places.find((p) => p.id === (placeId ?? COUNTRY_ID))
  const layers = data.catalogue.layers.filter((l) => l.section_id === section.id && l.kind !== 'boundary')
  const isOn = (layer: Layer) => activeLayers.some((l) => l.id === layer.id)
  const SectionIcon = sectionIcon(section.icon)
  const year = sectionData.status === 'ready' ? sectionData.data.year : null

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
        <span className="panel-icon">
          <SectionIcon size={26} aria-hidden />
        </span>
        <div className="panel-title">
          <h2>{section.title}</h2>
          {section.status !== 'coming-soon' && section.kind !== 'forecast' && (
            <p className="panel-place">
              {place?.name ?? 'Pakistan'}
              {year !== null && ` · ${year}`}
            </p>
          )}
        </div>
        <button type="button" aria-label="Close panel" onClick={() => viewStore.getState().closeSection()}>
          <X size={18} />
        </button>
      </header>

      {section.status === 'coming-soon' ? (
        <div className="panel-body">
          <p className="coming-soon">Coming soon</p>
          <p>{section.summary}</p>
        </div>
      ) : section.kind === 'forecast' ? (
        <div className="panel-body">
          <ForecastPanel forecast={data.catalogue.forecast ?? null} times={forecastTimes} />
        </div>
      ) : (
        <div className="panel-body">
          <Part
            icon={Layers}
            heading="Layers"
            count={layers.length > 0 ? `${layers.filter(isOn).length} of ${layers.length} on` : undefined}
          >
            {layers.length === 0 && (
              <p className="empty">
                {section.status === 'no-data' ? 'Data not loaded yet' : 'This section has no map layers.'}
              </p>
            )}
            {groupLayers(layers).map((group) => (
              <div key={group.scope ?? 'all'} className="layer-group">
                {group.scope && <h4>By {group.scope}</h4>}
                {group.layers.map((layer) => (
                  <LayerRow key={layer.id} layer={layer} on={isOn(layer)} />
                ))}
              </div>
            ))}
          </Part>
          <Part
            icon={Hash}
            heading={
              <>
                Figures for {place?.name ?? 'Pakistan'}
                {year !== null && `, ${year}`}
              </>
            }
          >
            {placeId !== null && (
              <p className="place-scope">
                {usedPlace && usedPlace.level === 'province'
                  ? `These are for ${usedPlace.name}, the province ${place?.name ?? 'this place'} is in.`
                  : 'These are for the place selected on the map.'}{' '}
                <button type="button" className="link-button" onClick={() => viewStore.getState().selectPlace(null)}>
                  Show all of Pakistan
                </button>
              </p>
            )}
            <Figures state={sectionData} placeSelected={placeId !== null} />
          </Part>
          <Part
            icon={BarChart3}
            heading="Charts"
            count={hasCharts ? String(sectionData.data.charts.length) : undefined}
            action={
              hasCharts && !full ? (
                <button type="button" className="full-view-button" onClick={() => viewStore.getState().setFull(true)}>
                  <Maximize2 size={16} aria-hidden /> Open charts in full view
                </button>
              ) : undefined
            }
          >
            {hasCharts && full ? (
              <p className="empty">
                The charts are open in full view.{' '}
                <button type="button" className="link-button" onClick={() => viewStore.getState().setFull(false)}>
                  Back to map
                </button>
              </p>
            ) : sectionData.status === 'ready' && sectionData.data.charts.length > 0 ? (
              sectionData.data.charts.map((chart) => (
                <div key={chart.id} className="chart-cell">
                  <ChartFigure spec={chart} year={sectionData.data.year} />
                  <button
                    type="button"
                    className="chart-size"
                    title="Maximize"
                    aria-label={`Maximize: ${chart.title}`}
                    onClick={() => viewStore.getState().maximize(chart.id)}
                  >
                    <Maximize2 size={17} aria-hidden />
                  </button>
                </div>
              ))
            ) : (
              <p className="empty">
                {sectionData.status === 'ready' ? 'No charts for this selection.' : 'Data not loaded yet'}
              </p>
            )}
          </Part>
        </div>
      )}
      <div className="panel-resize" onPointerDown={startResize} role="separator" aria-orientation="vertical" />
    </aside>
  )
}
