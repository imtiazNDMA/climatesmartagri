import { ChevronDown, ChevronUp, Eye, EyeOff, GripVertical, RotateCw, Trash2 } from 'lucide-react'
import { useState } from 'react'
import type { Catalogue } from '../api/types'
import { uiStore, useUi } from '../state/uiState'
import { useView, viewStore } from '../state/viewState'

export function ActiveLayers({ catalogue }: { catalogue: Catalogue }) {
  const layers = useView((s) => s.layers)
  const errors = useUi((s) => s.layerErrors)
  const [dragged, setDragged] = useState<string | null>(null)
  if (!layers.length) return null
  const view = viewStore.getState()

  return (
    <section className="active-layers" aria-label="Active layers">
      <h3>Active layers</h3>
      <ul>
        {layers.map((active, index) => {
          const title = catalogue.layers.find((l) => l.id === active.id)?.title ?? active.id
          return (
            <li
              key={active.id}
              onDragOver={(event) => event.preventDefault()}
              onDrop={() => {
                if (dragged) view.moveLayer(dragged, index)
                setDragged(null)
              }}
            >
              <div className="active-row">
                <span
                  className="active-grip"
                  draggable
                  title="Drag to reorder"
                  aria-hidden
                  onDragStart={() => setDragged(active.id)}
                >
                  <GripVertical size={14} />
                </span>
                <span className="active-title">{title}</span>
                <button
                  type="button" aria-label={`Move ${title} up`} disabled={index === 0}
                  onClick={() => view.moveLayer(active.id, index - 1)}
                >
                  <ChevronUp size={14} />
                </button>
                <button
                  type="button" aria-label={`Move ${title} down`} disabled={index === layers.length - 1}
                  onClick={() => view.moveLayer(active.id, index + 1)}
                >
                  <ChevronDown size={14} />
                </button>
                <button
                  type="button" aria-label={`${active.hidden ? 'Show' : 'Hide'} ${title}`}
                  onClick={() => view.toggleHidden(active.id)}
                >
                  {active.hidden ? <EyeOff size={14} /> : <Eye size={14} />}
                </button>
                <button type="button" aria-label={`Remove ${title}`} onClick={() => view.removeLayer(active.id)}>
                  <Trash2 size={14} />
                </button>
              </div>
              <input
                type="range" min={0} max={1} step={0.05} value={active.opacity}
                aria-label={`Opacity of ${title}`}
                onChange={(event) => view.setOpacity(active.id, Number(event.target.value))}
              />
              {errors[active.id] && (
                <div className="active-error">
                  <span>Could not load</span>
                  <button
                    type="button" aria-label={`Retry ${title}`}
                    onClick={() => uiStore.getState().retryLayer(active.id)}
                  >
                    <RotateCw size={12} /> Retry
                  </button>
                </div>
              )}
            </li>
          )
        })}
      </ul>
    </section>
  )
}
