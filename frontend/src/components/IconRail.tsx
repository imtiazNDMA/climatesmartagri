import {
  CalendarDays, CloudLightning, Droplets, Factory, Info, Square, Trees, Users, Waves, Wheat,
  type LucideIcon,
} from 'lucide-react'
import { useMemo } from 'react'
import type { Catalogue } from '../api/types'
import { sectionsWithActiveLayers } from '../state/selectors'
import { emptyView, useView, viewStore } from '../state/viewState'

const ICONS: Record<string, LucideIcon> = {
  trees: Trees,
  droplets: Droplets,
  factory: Factory,
  waves: Waves,
  wheat: Wheat,
  'calendar-days': CalendarDays,
  'cloud-lightning': CloudLightning,
  users: Users,
}

export function IconRail({ catalogue, onAbout }: { catalogue: Catalogue; onAbout: () => void }) {
  const open = useView((s) => s.section)
  const layers = useView((s) => s.layers)
  const marked = useMemo(() => sectionsWithActiveLayers({ ...emptyView, layers }, catalogue), [layers, catalogue])

  return (
    <nav className="rail" aria-label="Sections">
      <div className="rail-sections">
        {catalogue.sections.map((section) => {
          const Icon = ICONS[section.icon] ?? Square
          const soon = section.status === 'coming-soon'
          const label = soon ? `${section.title} (coming soon)` : section.title
          return (
            <button
              key={section.id}
              type="button"
              className={`rail-button${soon ? ' rail-soon' : ''}`}
              data-section={section.id}
              aria-label={label}
              aria-pressed={open === section.id}
              title={label}
              onClick={() => viewStore.getState().openSection(section.id)}
            >
              <Icon size={22} aria-hidden />
              {marked.has(section.id) && <span className="rail-dot" />}
              {soon && <span className="rail-soon-mark" aria-hidden>soon</span>}
            </button>
          )
        })}
      </div>
      <button type="button" className="rail-button" aria-label="About" title="About" onClick={onAbout}>
        <Info size={22} aria-hidden />
      </button>
    </nav>
  )
}
