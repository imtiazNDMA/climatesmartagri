import { useEffect, useRef } from 'react'

export function AboutDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const ref = useRef<HTMLDialogElement>(null)

  useEffect(() => {
    const dialog = ref.current
    if (!dialog) return
    if (open && !dialog.open) dialog.showModal()
    if (!open && dialog.open) dialog.close()
  }, [open])

  return (
    <dialog ref={ref} className="about" onClose={onClose}>
      <h2>Climate Smart Agriculture Portal</h2>
      <h3>Data sources</h3>
      <ul>
        <li>Irrigation practice and district irrigation figures: project datasets.</li>
        <li>Land cover: project rasters, loaded in a later release.</li>
        <li>Greenhouse-gas emissions: Our World in Data and national inventory figures, 1994–2021.</li>
        <li>Crop water balance and food security projections: project spreadsheets.</li>
        <li>Province and district boundaries: merged from the project's irrigation practice map layer.</li>
        <li>Background map: OpenFreeMap, © OpenStreetMap contributors.</li>
      </ul>
      <button type="button" onClick={onClose}>
        Close
      </button>
    </dialog>
  )
}
