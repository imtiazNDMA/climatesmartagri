// PROTOTYPE — throwaway. Three structurally different takes on the Weather forecast sidebar.
// A: a refined list with collapsible groups. B: a deck of cards under a "now showing" hero.
// C: a dark console that reads as a sentence, with a chip cloud. Styles are in forecastPrototype.css.
import {
  CalendarRange, Check, ChevronDown, ChevronLeft, ChevronRight, CloudRain, Droplets, Gauge, Search, Thermometer,
  Wind, X, type LucideIcon,
} from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import type { ForecastCatalogue, ForecastLayer } from '../api/types'
import type { ForecastTimesState } from '../data/useForecastTimes'
import { legendValues, levelLabel } from '../forecast/choice'
import {
  axisValues, buildEntries, setVariant, usePick, useVariant, VARIANTS, type Entry, type Pick,
} from './forecastEntries'
import './forecastPrototype.css'

const GROUP_ICONS: Record<string, LucideIcon> = {
  precipitation: CloudRain, dynamics: Wind, thermodynamics: Thermometer, moisture: Droplets, pressure: Gauge,
  outlook: CalendarRange,
}
const SHORT_GROUP: Record<string, string> = {
  precipitation: 'Rain', dynamics: 'Wind', thermodynamics: 'Heat', moisture: 'Moisture', pressure: 'Pressure',
  outlook: 'Outlook',
}
const ramp = (layer: ForecastLayer) => `linear-gradient(90deg, ${layer.colours.join(', ')})`
const entryRamp = (entry: Entry) => ramp((entry.options.find((o) => o.layer.id === entry.preferred) ?? entry.options[0]).layer)
const matches = (entry: Entry, query: string) => entry.title.toLowerCase().includes(query.trim().toLowerCase())

interface VariantProps {
  forecast: ForecastCatalogue
  entries: Entry[]
  unavailable: Record<string, string[]>
  pick: Pick
}

/** The key under the colours: the values at the ends, or at each colour when they are unevenly spread. */
function Scale({ pick, className }: { pick: Pick; className: string }) {
  if (!pick.layer || !pick.choice) return null
  const values = legendValues(pick.layer, pick.choice.level, pick.choice.model)
  return (
    <div className={className}>
      <span className="proto-scale-bar" style={{ background: ramp(pick.layer) }} />
      <span className="proto-scale-values">
        {values.map((value) => (
          <span key={value}>{value}</span>
        ))}
      </span>
    </div>
  )
}

// ---------------------------------------------------------------------------------------------------
// A — Refined list: quiet, dense, one group open at a time, the controls unfold under the chosen row.

function VariantA({ forecast, entries, unavailable, pick }: VariantProps) {
  const [query, setQuery] = useState('')
  const [open, setOpen] = useState<string | null>(pick.entry?.group ?? forecast.groups[0]?.id ?? null)
  const searching = query.trim() !== ''
  return (
    <div className="panel-body pa">
      <label className="pa-search">
        <Search size={16} aria-hidden />
        <input value={query} placeholder="Find a layer" aria-label="Find a layer" onChange={(e) => setQuery(e.target.value)} />
        {searching && (
          <button type="button" aria-label="Clear" onClick={() => setQuery('')}>
            <X size={14} />
          </button>
        )}
      </label>
      {forecast.groups.map((group) => {
        const rows = entries.filter((entry) => entry.group === group.id && matches(entry, query))
        if (searching && rows.length === 0) return null
        const Icon = GROUP_ICONS[group.id] ?? CloudRain
        const isOpen = searching || open === group.id
        const holdsChoice = pick.entry?.group === group.id
        return (
          <section key={group.id} className={`pa-group${isOpen ? ' open' : ''}`}>
            <button type="button" className="pa-group-head" aria-expanded={isOpen} onClick={() => setOpen(isOpen ? null : group.id)}>
              <span className="pa-group-icon"><Icon size={16} aria-hidden /></span>
              <span className="pa-group-title">{group.title}</span>
              {holdsChoice && !isOpen && <span className="pa-group-dot" aria-label="On the map" />}
              <span className="pa-group-count">{rows.length}</span>
              <ChevronDown size={16} className="pa-chevron" aria-hidden />
            </button>
            {isOpen && (
              <div className="pa-rows">
                {rows.map((entry) => {
                  const on = pick.entry?.id === entry.id
                  return (
                    <div key={entry.id} className={`pa-row${on ? ' on' : ''}`}>
                      <button type="button" className="pa-row-head" aria-pressed={on} onClick={() => pick.pickEntry(entry)}>
                        <span className="pa-swatch" style={{ background: entryRamp(entry) }} />
                        <span className="pa-row-title">{entry.title}</span>
                        <span className="pa-row-unit">{on ? pick.layer?.unit : entry.options[0].layer.unit}</span>
                        {on && <Check size={15} className="pa-check" aria-hidden />}
                      </button>
                      {on && (
                        <div className="pa-drawer">
                          {entry.axes.map((axis, i) => (
                            <div key={axis} className="pa-field">
                              <span>{axis}</span>
                              <div className="pa-seg">
                                {axisValues(entry, i, pick.labels).map((v) => (
                                  <button key={v.value} type="button" aria-pressed={v.on} className={v.fits ? '' : 'faint'} onClick={() => pick.pickAxis(i, v.value)}>
                                    {v.value}
                                  </button>
                                ))}
                              </div>
                            </div>
                          ))}
                          <div className="pa-field">
                            <span>Model</span>
                            <div className="pa-seg">
                              {pick.models.filter((m) => m.offers).map((m) => (
                                <button key={m.id} type="button" aria-pressed={m.on} onClick={() => pick.pickModel(m.id)}>
                                  {m.label}
                                </button>
                              ))}
                            </div>
                          </div>
                          {pick.levels.length > 1 && (
                            <div className="pa-field">
                              <span>Level</span>
                              <div className="pa-seg">
                                {pick.levels.map((level) => (
                                  <button key={level} type="button" aria-pressed={pick.choice?.level === level} onClick={() => pick.pickLevel(level)}>
                                    {levelLabel(level)}
                                  </button>
                                ))}
                              </div>
                            </div>
                          )}
                          <Scale pick={pick} className="pa-scale" />
                          <p className="pa-when">
                            {pick.status ?? (pick.when && <>Forecast for <strong>{pick.when}</strong> · run {pick.run}</>)}
                          </p>
                        </div>
                      )}
                    </div>
                  )
                })}
                {!searching && unavailable[group.id] && (
                  <p className="pa-missing">Not available from PMD now: {unavailable[group.id].join(', ')}</p>
                )}
              </div>
            )}
          </section>
        )
      })}
    </div>
  )
}

// ---------------------------------------------------------------------------------------------------
// B — Card deck: what is on the map leads as an instrument readout over the layer's own "weather field";
// the layers are a grid of cards, each with a small field of its colours in place of a flat strip.

/** A number from a string, the same every time, so each layer keeps its own pattern. */
function seedOf(text: string): number {
  let seed = 2166136261
  for (let i = 0; i < text.length; i++) seed = Math.imul(seed ^ text.charCodeAt(i), 16777619)
  return seed >>> 0
}

/**
 * A layer's colours drawn as a small weather chart: soft patches of high and low over the scale, with faint
 * contour rings round one of them. Built from CSS gradients alone.
 */
function field(colours: string[], key: string): string {
  let state = seedOf(key)
  const next = () => {
    state = (Math.imul(state, 1664525) + 1013904223) >>> 0
    return state / 4294967296
  }
  const last = colours.length - 1
  const at = (share: number) => colours[Math.round(share * last)]
  const patch = (colour: string, size: number) =>
    `radial-gradient(ellipse ${size}% ${size * 0.8}% at ${Math.round(8 + next() * 84)}% ${Math.round(10 + next() * 80)}%, ${colour} 0%, transparent 72%)`
  const ringX = Math.round(20 + next() * 60)
  const ringY = Math.round(20 + next() * 60)
  return [
    `repeating-radial-gradient(circle at ${ringX}% ${ringY}%, transparent 0 13px, rgb(255 255 255 / 20%) 13px 14px)`,
    patch(at(1), 46),
    patch(at(0), 52),
    patch(at(0.75), 40),
    patch(at(0.25), 44),
    `linear-gradient(${Math.round(next() * 360)}deg, ${at(0.15)}, ${at(0.5)}, ${at(0.85)})`,
  ].join(', ')
}

function VariantB({ forecast, entries, unavailable, pick }: VariantProps) {
  const [group, setGroup] = useState(pick.entry?.group ?? forecast.groups[0]?.id ?? '')
  const cards = entries.filter((entry) => entry.group === group)
  const values = pick.layer && pick.choice ? legendValues(pick.layer, pick.choice.level, pick.choice.model) : []
  const [date, clock] = pick.when ? pick.when.split(', ') : ['', '']
  return (
    <div className="panel-body pb">
      {pick.layer && pick.entry && pick.choice ? (
        // Keyed by layer, so a new choice fades its own field in over the last.
        <section className="pb-hero" key={pick.layer.id} aria-label="On the map">
          <div className="pb-hero-field" style={{ backgroundImage: field(pick.layer.colours, pick.entry.id) }}>
            <button type="button" className="pb-hero-close" aria-label="Remove from map" onClick={pick.clear}>
              <X size={15} />
            </button>
            <h3>{pick.layer.title}</h3>
            {pick.status ? (
              <p className="pb-hero-status" role="status">{pick.status}</p>
            ) : (
              pick.when && (
                <p className="pb-hero-time">
                  <strong>{clock}</strong>
                  <span>
                    {date}
                    <small>Pakistan time, from the {pick.run} run</small>
                  </span>
                </p>
              )
            )}
          </div>

          <div className="pb-gauge">
            <span className="pb-gauge-bar" style={{ background: ramp(pick.layer) }} />
            <span className="pb-gauge-ticks">
              {values.map((value) => (
                <span key={value}>{value}</span>
              ))}
            </span>
            <span className="pb-gauge-unit">{pick.layer.unit}</span>
          </div>

          <div className="pb-controls">
            {pick.entry.axes.map((axis, i) => (
              <div key={axis} className="pb-control">
                <span>{axis}</span>
                <div className="pb-track" role="group" aria-label={axis}>
                  {axisValues(pick.entry!, i, pick.labels).map((v) => (
                    <button key={v.value} type="button" aria-pressed={v.on} className={v.fits ? '' : 'faint'} onClick={() => pick.pickAxis(i, v.value)}>
                      {v.value}
                    </button>
                  ))}
                </div>
              </div>
            ))}
            <div className="pb-control">
              <span>Model</span>
              <div className="pb-choices" role="group" aria-label="Model">
                {pick.models.filter((m) => m.offers).map((m) => (
                  <button key={m.id} type="button" aria-pressed={m.on} onClick={() => pick.pickModel(m.id)}>
                    {m.label}
                  </button>
                ))}
              </div>
            </div>
            {pick.levels.length > 1 && (
              <div className="pb-control">
                <span>Level</span>
                <div className="pb-track" role="group" aria-label="Level">
                  {pick.levels.map((level) => (
                    <button key={level} type="button" aria-pressed={pick.choice?.level === level} onClick={() => pick.pickLevel(level)}>
                      {level === 0 ? 'Surface' : level}
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>
        </section>
      ) : (
        <section className="pb-hero pb-hero-empty">
          <div className="pb-hero-field" style={{ backgroundImage: field(['#dbe7f5', '#b9cfe8', '#8fb0d6', '#b9cfe8', '#eef3f9'], 'empty') }}>
            <h3>Nothing on the map yet</h3>
            <p className="pb-hero-status">Choose a layer below to draw it.</p>
          </div>
        </section>
      )}

      <div className="pb-tabs" role="tablist" aria-label="Kinds of layer">
        {forecast.groups.map((g) => {
          const Icon = GROUP_ICONS[g.id] ?? CloudRain
          return (
            <button key={g.id} type="button" role="tab" aria-selected={group === g.id} title={g.title} onClick={() => setGroup(g.id)}>
              <Icon size={18} aria-hidden />
              <span>{SHORT_GROUP[g.id] ?? g.title}</span>
              {pick.entry?.group === g.id && <i aria-label="On the map" />}
            </button>
          )
        })}
      </div>

      <div className="pb-grid">
        {cards.map((entry) => {
          const on = pick.entry?.id === entry.id
          const first = entry.options.find((o) => o.layer.id === entry.preferred) ?? entry.options[0]
          const kinds = entry.axes.length ? [...new Set(entry.options.map((o) => o.labels[0]))].join(', ') : first.layer.unit
          return (
            <button key={entry.id} type="button" className={`pb-card${on ? ' on' : ''}`} aria-pressed={on} onClick={() => pick.pickEntry(entry)}>
              <span className="pb-card-field" style={{ backgroundImage: field(first.layer.colours, entry.id) }}>
                {on && <span className="pb-card-on"><Check size={13} aria-hidden /></span>}
              </span>
              <span className="pb-card-title">{entry.title}</span>
              <span className="pb-card-meta">{kinds || 'No unit'}</span>
            </button>
          )
        })}
      </div>
      {unavailable[group] && <p className="pb-missing">PMD has no current data for {unavailable[group].join(', ')}.</p>}
    </div>
  )
}

// ---------------------------------------------------------------------------------------------------
// C — Dark console: the choice reads as a sentence; layers are a cloud of chips; levels are a ladder by height.

function VariantC({ forecast, entries, unavailable, pick }: VariantProps) {
  const [group, setGroup] = useState<string>('all')
  const [query, setQuery] = useState('')
  const shown = entries.filter((entry) => (group === 'all' || entry.group === group) && matches(entry, query))
  const missing = group === 'all' ? Object.values(unavailable).flat() : (unavailable[group] ?? [])
  const model = pick.models.find((m) => m.on)
  return (
    <div className="panel-body pc">
      <div className="pc-sentence">
        {pick.layer && pick.choice ? (
          <>
            <span className="pc-word">Showing</span>
            <strong style={{ backgroundImage: ramp(pick.layer) }}>{pick.layer.title}</strong>
            <span className="pc-word">from</span>
            <strong className="plain">{model?.label}</strong>
            {pick.levels.length > 1 && (
              <>
                <span className="pc-word">at</span>
                <strong className="plain">{levelLabel(pick.choice.level)}</strong>
              </>
            )}
            <button type="button" className="pc-clear" onClick={pick.clear}>Clear</button>
            <Scale pick={pick} className="pc-scale" />
            <p className="pc-when">{pick.status ?? (pick.when ? `${pick.when} Pakistan time · run ${pick.run}` : '')}</p>
          </>
        ) : (
          <span className="pc-word">Nothing on the map yet. Choose a layer.</span>
        )}
      </div>

      {pick.entry && pick.layer && pick.choice && (
        <div className="pc-detail">
          <div className="pc-detail-main">
            {pick.entry.axes.map((axis, i) => (
              <div key={axis} className="pc-block">
                <h4>{axis}</h4>
                <div className="pc-seg">
                  {axisValues(pick.entry!, i, pick.labels).map((v) => (
                    <button key={v.value} type="button" aria-pressed={v.on} className={v.fits ? '' : 'faint'} onClick={() => pick.pickAxis(i, v.value)}>
                      {v.value}
                    </button>
                  ))}
                </div>
              </div>
            ))}
            <div className="pc-block">
              <h4>Model</h4>
              <div className="pc-models">
                {pick.models.map((m) => (
                  <button key={m.id} type="button" aria-pressed={m.on} disabled={!m.offers} onClick={() => pick.pickModel(m.id)}>
                    <span className="pc-led" />
                    {m.label}
                  </button>
                ))}
              </div>
            </div>
          </div>
          {pick.levels.length > 1 && (
            <div className="pc-block pc-ladder-block">
              <h4>Height</h4>
              <div className="pc-ladder">
                {[...pick.levels].sort((a, b) => (a === 0 ? 1 : b === 0 ? -1 : a - b)).map((level) => (
                  <button key={level} type="button" aria-pressed={pick.choice?.level === level} onClick={() => pick.pickLevel(level)}>
                    {levelLabel(level)}
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      <label className="pc-search">
        <Search size={15} aria-hidden />
        <input value={query} placeholder="Search layers" aria-label="Search layers" onChange={(e) => setQuery(e.target.value)} />
      </label>
      <div className="pc-tabs" role="tablist" aria-label="Kinds of layer">
        <button type="button" role="tab" aria-selected={group === 'all'} onClick={() => setGroup('all')}>All</button>
        {forecast.groups.map((g) => (
          <button key={g.id} type="button" role="tab" aria-selected={group === g.id} onClick={() => setGroup(g.id)}>
            {SHORT_GROUP[g.id] ?? g.title}
          </button>
        ))}
      </div>
      <div className="pc-cloud">
        {shown.map((entry) => {
          const on = pick.entry?.id === entry.id
          return (
            <button key={entry.id} type="button" className={`pc-chip${on ? ' on' : ''}`} aria-pressed={on} onClick={() => pick.pickEntry(entry)}>
              <span className="pc-chip-dot" style={{ background: entryRamp(entry) }} />
              {entry.title}
            </button>
          )
        })}
      </div>
      {missing.length > 0 && query === '' && <p className="pc-missing">No current data from PMD: {missing.join(' · ')}</p>}
    </div>
  )
}

// ---------------------------------------------------------------------------------------------------

/** The variant chosen in the floating bar, or null for the panel as it is today. */
export function ForecastPrototype({ forecast, times }: { forecast: ForecastCatalogue; times: ForecastTimesState }) {
  const variant = useVariant()
  const built = useMemo(() => buildEntries(forecast), [forecast])
  const pick = usePick(forecast, built.entries, times)
  const props = { forecast, pick, ...built }
  if (variant === 'A') return <VariantA {...props} />
  if (variant === 'B') return <VariantB {...props} />
  if (variant === 'C') return <VariantC {...props} />
  return null
}

/** The floating bar that flips between variants. Left and right arrow keys do the same. */
export function PrototypeSwitcher() {
  const variant = useVariant()
  const at = VARIANTS.findIndex((v) => v.key === variant)
  useEffect(() => {
    const step = (by: number) => setVariant(VARIANTS[(at + by + VARIANTS.length) % VARIANTS.length].key)
    const onKey = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null
      if (target?.closest('input, textarea, select, [contenteditable]')) return
      if (event.key === 'ArrowLeft') step(-1)
      if (event.key === 'ArrowRight') step(1)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [at])
  const step = (by: number) => setVariant(VARIANTS[(at + by + VARIANTS.length) % VARIANTS.length].key)
  return (
    <div className="proto-switcher" role="group" aria-label="Prototype variant">
      <button type="button" aria-label="Previous variant" onClick={() => step(-1)}><ChevronLeft size={16} /></button>
      <span>
        <small>Sidebar prototype</small>
        {variant === 'current' ? VARIANTS[at].name : `${variant} — ${VARIANTS[at].name}`}
      </span>
      <button type="button" aria-label="Next variant" onClick={() => step(1)}><ChevronRight size={16} /></button>
    </div>
  )
}

export { useVariant }
