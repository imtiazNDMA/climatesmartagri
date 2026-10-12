import { CalendarRange, Check, CloudRain, Droplets, Gauge, Thermometer, Wind, X, type LucideIcon } from 'lucide-react'
import {
  useEffect, useLayoutEffect, useMemo, useRef, useState, type CSSProperties, type ReactNode, type RefObject,
} from 'react'
import type { ForecastCatalogue, ForecastLayer } from '../api/types'
import type { ForecastTimesState } from '../data/useForecastTimes'
import {
  chooseLayer, chooseModel, formatRun, formatTime, legendValues, levelLabel, levelsFor, timeAtShare,
  type ForecastChoice,
} from '../forecast/choice'
import { axisValues, buildEntries, entryOf, firstLayer, layerForAxis, type Entry } from '../forecast/entries'
import { useUi } from '../state/uiState'
import { useView, viewStore } from '../state/viewState'
import { drawGauge, flyArt, runShare } from './deckMotion'
import { fieldArt, fieldRings } from './fieldArt'

/** A picture and a short name for each kind of layer, by the group's id; a group not listed uses its own title. */
const GROUPS: Record<string, { icon: LucideIcon; short: string }> = {
  precipitation: { icon: CloudRain, short: 'Rain' },
  dynamics: { icon: Wind, short: 'Wind' },
  thermodynamics: { icon: Thermometer, short: 'Heat' },
  moisture: { icon: Droplets, short: 'Moisture' },
  pressure: { icon: Gauge, short: 'Pressure' },
  outlook: { icon: CalendarRange, short: 'Outlook' },
}

const ramp = (layer: ForecastLayer) => `linear-gradient(90deg, ${layer.colours.join(', ')})`

/** Where a picked card's picture was on screen, and the picture, for carrying it up into the banner. */
interface Departure {
  rect: DOMRect
  art: string
}

/** Why the forecast is not on the map yet, in words, or null when it is or soon will be. */
function problemWith(times: ForecastTimesState): string | null {
  if (times.status === 'loading') return 'Asking PMD which times it has…'
  if (times.status === 'ready' && times.times.length === 0) return 'PMD has no recent files for this choice.'
  if (times.status !== 'error') return null
  if (times.reason === 'not-configured') return 'The forecast source is not set up on this server.'
  if (times.reason === 'source-unreachable') return 'PMD’s server is not answering. Try again in a moment.'
  return `The forecast could not be loaded: ${times.message}`
}

/**
 * Choices of one kind side by side, of which one is on. A pill lies under the one that is on and slides
 * to another when it is picked, so the eye follows the change instead of finding it.
 */
function Track({ className, role, label, children }: {
  className: string
  role: 'group' | 'tablist'
  label: string
  children: ReactNode
}) {
  const track = useRef<HTMLDivElement>(null)
  const pill = useRef<HTMLSpanElement>(null)

  useLayoutEffect(() => {
    const place = () => {
      const on = track.current?.querySelector<HTMLElement>('[aria-pressed="true"], [aria-selected="true"]')
      if (!pill.current) return
      if (!on) {
        pill.current.style.opacity = '0'
        return
      }
      Object.assign(pill.current.style, {
        opacity: '1', width: `${on.offsetWidth}px`, height: `${on.offsetHeight}px`,
        transform: `translate(${on.offsetLeft}px, ${on.offsetTop}px)`,
      })
    }
    place()
    // The pill slides only once it has been put down the first time, and keeps its place if the panel is resized.
    const settled = requestAnimationFrame(() => pill.current?.classList.add('settled'))
    const resized = new ResizeObserver(place)
    if (track.current) resized.observe(track.current)
    return () => {
      cancelAnimationFrame(settled)
      resized.disconnect()
    }
  })

  return (
    <div ref={track} className={`${className} deck-sliding`} role={role} aria-label={label}>
      <span ref={pill} className="deck-pill" aria-hidden />
      {children}
    </div>
  )
}

/** A time that rolls from the one before to the new one, hour by hour, instead of jumping. */
function useRolledTime(time: string | undefined): string | undefined {
  const [shown, setShown] = useState(time)
  const last = useRef(time)
  useEffect(() => {
    const from = last.current
    last.current = time
    if (!time || !from || from === time) {
      setShown(time)
      return
    }
    return runShare((share) => setShown(timeAtShare(from, time, share)))
  }, [time])
  return shown
}

/** What is on the map: the time it is for, its scale, and the buttons that change how it is cut. */
function Showing({ forecast, entry, layer, choice, times, departure }: {
  forecast: ForecastCatalogue
  entry: Entry
  layer: ForecastLayer
  choice: ForecastChoice
  times: ForecastTimesState
  departure: RefObject<Departure | null>
}) {
  const tileError = useUi((s) => s.layerErrors.forecast ?? false)
  const fetching = useUi((s) => s.forecastLoading)
  const art = useRef<HTMLDivElement>(null)
  const gauge = useRef<HTMLDivElement>(null)
  const set = (next: ForecastChoice | null) => viewStore.getState().setForecast(next)
  const labels = entry.options.find((option) => option.layer.id === layer.id)?.labels
  const levels = levelsFor(layer, choice.model)
  const slot = times.status === 'ready' ? times.times.find((t) => t.time === choice.time) : undefined
  const problem = problemWith(times)
  const rolled = useRolledTime(slot?.time)
  const [date, clock] = rolled ? formatTime(rolled).split(', ') : ['', '']
  const values = legendValues(layer, choice.level, choice.model)

  // This banner is new for each layer: its scale draws in, and the card it was picked from flies up to it.
  useLayoutEffect(() => {
    if (gauge.current) drawGauge(gauge.current)
    if (departure.current && art.current) flyArt(departure.current.rect, art.current, departure.current.art)
    departure.current = null
  }, [departure])

  return (
    <section className="deck-hero" aria-label="On the map">
      <div ref={art} className="deck-hero-art" style={{ backgroundImage: fieldArt(layer.colours, entry.id, { rings: false }) }}>
        {/* The contour rings are a layer of their own, so they can drift a little, like a chart that is live. */}
        <span className="deck-hero-rings" style={{ backgroundImage: fieldRings(entry.id) }} aria-hidden />
        <button type="button" className="deck-hero-close" aria-label="Remove from map" onClick={() => set(null)}>
          <X size={15} aria-hidden />
        </button>
        <h3>{layer.title}</h3>
        {problem ? (
          <p className="deck-hero-note" role="status">{problem}</p>
        ) : tileError ? (
          <p className="deck-hero-note" role="alert">This time could not be fetched from PMD. Try another time.</p>
        ) : (
          slot && (
            <p className="deck-hero-time">
              <strong>{clock}</strong>
              <span>
                {date}
                <small>Pakistan time, from the {formatRun(slot.run)} run</small>
              </span>
            </p>
          )
        )}
        {!problem && !tileError && fetching && (
          <p className="deck-hero-fetching" role="status">Fetching this time from PMD…</p>
        )}
      </div>

      <div ref={gauge} className="deck-gauge" aria-hidden>
        <span className="deck-gauge-bar" style={{ background: ramp(layer) }} />
        <span className="deck-gauge-ticks">
          {values.map((value) => (
            <span key={value}>{value}</span>
          ))}
        </span>
        <span className="deck-gauge-unit">{layer.unit}</span>
      </div>

      <div className="deck-controls">
        {entry.axes.map((axis, at) => (
          <div key={axis} className="deck-control">
            <span>{axis}</span>
            <Track className="deck-track" role="group" label={axis}>
              {axisValues(entry, at, labels).map((option) => (
                <button
                  key={option.value}
                  type="button"
                  aria-pressed={option.on}
                  className={option.fits ? undefined : 'deck-faint'}
                  onClick={() => {
                    const next = layerForAxis(entry, labels, at, option.value)
                    if (next) set(chooseLayer(forecast, next.id, choice))
                  }}
                >
                  {option.value}
                </button>
              ))}
            </Track>
          </div>
        ))}
        <div className="deck-control">
          <span>Model</span>
          <div className="deck-choices" role="group" aria-label="Model">
            {forecast.models
              .filter((model) => levelsFor(layer, model.id).length > 0)
              .map((model) => (
                <button
                  key={model.id}
                  type="button"
                  aria-pressed={choice.model === model.id}
                  onClick={() => set(chooseModel(layer, model.id, choice))}
                >
                  {model.label}
                </button>
              ))}
          </div>
        </div>
        {levels.length > 1 && (
          <div className="deck-control">
            <span>Level</span>
            <Track className="deck-track" role="group" label="Level">
              {levels.map((level) => (
                <button
                  key={level}
                  type="button"
                  aria-label={levelLabel(level)}
                  title={levelLabel(level)}
                  aria-pressed={choice.level === level}
                  onClick={() => set({ ...choice, level })}
                >
                  {level === 0 ? 'Surface' : level}
                </button>
              ))}
            </Track>
          </div>
        )}
      </div>
    </section>
  )
}

export function ForecastPanel({ forecast, times }: { forecast: ForecastCatalogue | null; times: ForecastTimesState }) {
  const choice = useView((s) => s.forecast)
  const built = useMemo(() => (forecast ? buildEntries(forecast) : { entries: [], unavailable: {} }), [forecast])
  const entry = entryOf(built.entries, choice?.layer)
  const [picked, setPicked] = useState<string | null>(null)
  const departure = useRef<Departure | null>(null)
  if (!forecast) return <p className="empty">Data not loaded yet</p>

  const layer = forecast.layers.find((l) => l.id === choice?.layer)
  // The kind of layer shown: the one last opened, else the one the forecast on the map belongs to, else the first.
  const group = picked ?? entry?.group ?? forecast.groups[0]?.id ?? ''
  const cards = built.entries.filter((e) => e.group === group)
  const missing: string[] = (built.unavailable as Record<string, string[]>)[group] ?? []
  const toggle = (target: Entry, card: HTMLElement | null) => {
    const turningOn = target.id !== entry?.id
    const picture = card?.querySelector<HTMLElement>('.deck-card-art')
    departure.current =
      turningOn && picture ? { rect: picture.getBoundingClientRect(), art: picture.style.backgroundImage } : null
    viewStore.getState().setForecast(turningOn ? chooseLayer(forecast, firstLayer(target).id, choice) : null)
  }

  return (
    <div className="deck">
      {!forecast.configured && (
        <p className="deck-warning" role="status">The forecast source is not set up on this server.</p>
      )}
      {choice && layer && entry ? (
        // Keyed by layer, so a new choice arrives as a new banner with its own picture.
        <Showing
          key={layer.id} forecast={forecast} entry={entry} layer={layer} choice={choice} times={times}
          departure={departure}
        />
      ) : (
        <section className="deck-hero deck-hero-empty" aria-label="On the map">
          <div className="deck-hero-art" style={{ backgroundImage: fieldArt(['#dbe7f5', '#b9cfe8', '#8fb0d6', '#b9cfe8', '#eef3f9'], 'empty') }}>
            <h3>Nothing on the map yet</h3>
            <p className="deck-hero-note">Choose a layer below to draw it.</p>
          </div>
        </section>
      )}

      <Track className="deck-tabs" role="tablist" label="Kinds of layer">
        {forecast.groups.map((g) => {
          const Icon = GROUPS[g.id]?.icon ?? CloudRain
          return (
            <button key={g.id} type="button" role="tab" aria-selected={group === g.id} aria-label={g.title} title={g.title} onClick={() => setPicked(g.id)}>
              <Icon size={18} aria-hidden />
              <span>{GROUPS[g.id]?.short ?? g.title}</span>
              {entry?.group === g.id && <i title="On the map" />}
            </button>
          )
        })}
      </Track>

      {/* Keyed by kind, so the cards of a newly opened kind arrive together. */}
      <div className="deck-grid" key={group}>
        {cards.map((card, at) => {
          const on = card.id === entry?.id
          const first = firstLayer(card)
          const about = card.axes.length ? [...new Set(card.options.map((o) => o.labels[0]))].join(', ') : first.unit
          return (
            <label key={card.id} className={`deck-card${on ? ' on' : ''}`} style={{ '--at': at } as CSSProperties}>
              <input
                type="checkbox" role="switch" aria-label={card.title} checked={on}
                onChange={(event) => toggle(card, event.currentTarget.closest('.deck-card'))}
              />
              <span className="deck-card-art" style={{ backgroundImage: fieldArt(first.colours, card.id) }}>
                {on && <span className="deck-card-on"><Check size={13} aria-hidden /></span>}
              </span>
              <span className="deck-card-title">{card.title}</span>
              <span className="deck-card-about">{about || 'No unit'}</span>
            </label>
          )
        })}
      </div>
      {missing.length > 0 && <p className="deck-missing">PMD has no current data for {missing.join(', ')}.</p>}
    </div>
  )
}
