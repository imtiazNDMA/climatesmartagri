import { Droplets, ShowerHead, Sprout, Waves, type LucideIcon } from 'lucide-react'
import { useEffect, useState, type CSSProperties } from 'react'
import { labelParts, leadingNumber, type TooltipPoint, type TooltipTable } from '../map/tooltip'

/** The picture for each irrigation practice, by the name the data gives it. */
export const ICONS: Record<string, LucideIcon> = { drip: Droplets, sprinkler: ShowerHead, paddy: Sprout, flood: Waves }
const COUNT_MS = 550

/** What one visible layer says about the clicked spot. */
export interface PopupBlock {
  layerId: string
  layerTitle: string
  /** The colour the clicked shape has on the map, so the card visibly belongs to it. */
  colour: string
  label: string
  table: TooltipTable | null
}

/** A value whose opening number runs up from zero when the card opens. Other values are shown as they are. */
function CountUp({ value }: { value: string }) {
  const parsed = leadingNumber(value)
  const still = !parsed || window.matchMedia('(prefers-reduced-motion: reduce)').matches
  const [share, setShare] = useState(still ? 1 : 0)

  useEffect(() => {
    if (still) return
    let frame = 0
    const started = performance.now()
    const step = (now: number) => {
      const elapsed = Math.min(1, (now - started) / COUNT_MS)
      // Fast at first, easing into the final figure.
      setShare(1 - (1 - elapsed) ** 3)
      if (elapsed < 1) frame = requestAnimationFrame(step)
    }
    frame = requestAnimationFrame(step)
    return () => cancelAnimationFrame(frame)
  }, [still, value])

  if (!parsed || share >= 1) return <>{value}</>
  const shown = (parsed.number * share).toLocaleString('en-US', {
    minimumFractionDigits: parsed.decimals,
    maximumFractionDigits: parsed.decimals,
  })
  return (
    <>
      {shown}
      {parsed.rest}
    </>
  )
}

function Point({ point }: { point: TooltipPoint }) {
  return (
    <p>
      {point.label && <span className={`popup-pill popup-pill-${point.tone ?? 'plain'}`}>{point.label}</span>}
      {(point.parts ?? [{ text: point.text }]).map((part, index) =>
        part.tone ? (
          <mark key={index} className={`popup-mark popup-mark-${part.tone}`}>
            {part.text}
          </mark>
        ) : (
          part.text
        ),
      )}
    </p>
  )
}

function Table({ table }: { table: TooltipTable }) {
  return (
    <table className="popup-table">
      {table.title && <caption>{table.title}</caption>}
      <thead>
        <tr>
          {table.columns.map((column) => (
            <th key={column} scope="col">
              {column}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {table.rows.map((row, index) => {
          const Icon = row.icon ? ICONS[row.icon] : undefined
          return (
            // Rows arrive one after another, each a moment behind the one above.
            <tr key={row.name} style={{ '--row': index } as CSSProperties}>
              <th scope="row">
                <span className="popup-type">
                  {Icon && (
                    <span className={`popup-icon popup-icon-${row.icon}`}>
                      <Icon size={22} aria-hidden />
                    </span>
                  )}
                  {row.name}
                </span>
              </th>
              <td>
                {row.points.map((point) => (
                  <Point key={point.label ?? point.text} point={point} />
                ))}
              </td>
            </tr>
          )
        })}
      </tbody>
    </table>
  )
}

/** The card shown where the map is clicked: the place, then one block for each visible shape layer. */
export function MapPopup({ place, parent, blocks }: { place: string; parent: string | null; blocks: PopupBlock[] }) {
  // The card wears the colour of the topmost shape under the click: a strip of it, and a tint behind the name.
  const shape = blocks[0]?.colour
  return (
    <div className="popup-card" style={shape ? ({ '--shape': shape } as CSSProperties) : undefined}>
      <header className="popup-head">
        <strong>{place}</strong>
        {parent && <span>{parent}</span>}
      </header>
      {blocks.map((block) => {
        if (block.table) {
          return (
            <section key={block.layerId} className="popup-block" style={{ borderLeftColor: block.colour }}>
              <Table table={block.table} />
            </section>
          )
        }
        const { name, value } = labelParts(block.label)
        return (
          <section key={block.layerId} className="popup-block" style={{ borderLeftColor: block.colour }}>
            {name && <span className="popup-measure">{name}</span>}
            {name ? (
              <span className="popup-value">
                <CountUp key={value} value={value} />
              </span>
            ) : (
              <span className="popup-sentence">{value}</span>
            )}
          </section>
        )
      })}
    </div>
  )
}
