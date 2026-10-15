import { Bot, Info } from 'lucide-react'
import { useMemo } from 'react'
import type { Catalogue } from '../api/types'
import { sectionsWithActiveLayers } from '../state/selectors'
import { emptyView, useView, viewStore } from '../state/viewState'
import { sectionIcon } from './sectionIcons'

type IconRailProps = {
  catalogue: Catalogue
  onAbout: () => void
  onAssistant: () => void
}

export function IconRail({ catalogue, onAbout, onAssistant }: IconRailProps) {
  const open = useView((s) => s.section)
  const layers = useView((s) => s.layers)
  const forecastOn = useView((s) => s.forecast !== null)
  const marked = useMemo(() => sectionsWithActiveLayers({ ...emptyView, layers }, catalogue), [layers, catalogue])

  return (
    <nav className="rail" aria-label="Sections">
      <div className="rail-sections">
        {catalogue.sections.map((section) => {
          const Icon = sectionIcon(section.icon)
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
              {(marked.has(section.id) || (forecastOn && section.kind === 'forecast')) && <span className="rail-dot" />}
              {soon && <span className="rail-soon-mark" aria-hidden>soon</span>}
            </button>
          )
        })}
      </div>
      <div className="rail-footer">
        <button type="button" className="rail-button" aria-label="AI portal guide" title="AI portal guide" onClick={onAssistant}>
          <Bot size={22} aria-hidden />
        </button>
        <button type="button" className="rail-button" aria-label="About" title="About" onClick={onAbout}>
          <Info size={22} aria-hidden />
        </button>
      </div>
    </nav>
  )
}
