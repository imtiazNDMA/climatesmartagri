import { Check, Layers3, X } from 'lucide-react'
import { useState } from 'react'
import { BASEMAPS, type BasemapId } from '../map/basemaps'

export function BasemapSelector({ value, onChange }: { value: BasemapId; onChange: (id: BasemapId) => void }) {
  const [open, setOpen] = useState(false)
  const selected = BASEMAPS.find((basemap) => basemap.id === value) ?? BASEMAPS[0]
  return (
    <div className="basemap-selector">
      <button
        type="button"
        className="basemap-trigger"
        aria-label={`Basemap: ${selected.label}`}
        aria-expanded={open}
        onClick={() => setOpen((current) => !current)}
      >
        <Layers3 size={18} aria-hidden />
        <span>{selected.label}</span>
      </button>
      {open && (
        <div className="basemap-menu" role="dialog" aria-label="Choose a basemap">
          <header>
            <strong>Basemap</strong>
            <button type="button" aria-label="Close basemap menu" onClick={() => setOpen(false)}><X size={17} /></button>
          </header>
          <div className="basemap-options">
            {BASEMAPS.map((basemap) => (
              <button
                type="button"
                key={basemap.id}
                className={basemap.id === value ? 'selected' : ''}
                onClick={() => { onChange(basemap.id); setOpen(false) }}
              >
                <span className={`basemap-preview basemap-preview-${basemap.id}`} aria-hidden />
                <span><strong>{basemap.label}</strong><small>{basemap.description}</small></span>
                {basemap.id === value && <Check size={17} aria-hidden />}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
