import { useState } from 'react'
import { AboutDialog } from './components/AboutDialog'
import { ActiveLayers } from './components/ActiveLayers'
import { BackendDown } from './components/BackendDown'
import { IconRail } from './components/IconRail'
import { Legend } from './components/Legend'
import { MapView } from './components/MapView'
import { Notices } from './components/Notices'
import { SectionPanel } from './components/SectionPanel'
import { TimeSlider } from './components/TimeSlider'
import { useLayerProbes } from './data/useLayerProbes'
import { usePortalData, type PortalData } from './data/usePortalData'
import { useUrlSync } from './state/useUrlSync'

function Portal({ data }: { data: PortalData }) {
  useUrlSync(data.catalogue, data.places)
  useLayerProbes(data.catalogue)
  const [aboutOpen, setAboutOpen] = useState(false)
  return (
    <div className="app">
      <IconRail catalogue={data.catalogue} onAbout={() => setAboutOpen(true)} />
      <SectionPanel data={data} />
      <main className="map-area">
        <MapView data={data} />
        <ActiveLayers catalogue={data.catalogue} />
        <Legend catalogue={data.catalogue} />
        <TimeSlider catalogue={data.catalogue} />
        <Notices />
      </main>
      <AboutDialog open={aboutOpen} onClose={() => setAboutOpen(false)} />
    </div>
  )
}

export default function App() {
  const { state, retry } = usePortalData()
  if (state.status === 'loading') return <div className="splash">Loading the portal…</div>
  if (state.status === 'unreachable') return <BackendDown onRetry={retry} />
  if (state.status === 'error') {
    return (
      <div className="backend-down" role="alert">
        <h1>The portal could not load its data</h1>
        <p>{state.message}</p>
        <button type="button" onClick={retry}>
          Try again
        </button>
      </div>
    )
  }
  return <Portal data={state.data} />
}
