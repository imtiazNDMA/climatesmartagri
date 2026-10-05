import { useState } from 'react'
import { AboutDialog } from './components/AboutDialog'
import { ActiveLayers } from './components/ActiveLayers'
import { BackendDown } from './components/BackendDown'
import { ChartsView } from './components/ChartsView'
import { Breadcrumb } from './components/Breadcrumb'
import { IconRail } from './components/IconRail'
import { Legend } from './components/Legend'
import { MapView } from './components/MapView'
import { Notices } from './components/Notices'
import { PlaceSearch } from './components/PlaceSearch'
import { SectionPanel } from './components/SectionPanel'
import { TimeSlider } from './components/TimeSlider'
import { useBackendWatch } from './data/useBackendWatch'
import { useLayerProbes } from './data/useLayerProbes'
import { usePortalData, type PortalData } from './data/usePortalData'
import { useSectionData } from './data/useSectionData'
import { COUNTRY_ID } from './api/types'
import { effectiveYear } from './state/selectors'
import { useView } from './state/viewState'
import { useUrlSync } from './state/useUrlSync'

function Portal({ data, onLayersChanged }: { data: PortalData; onLayersChanged: () => void }) {
  useUrlSync(data.catalogue, data.places)
  useLayerProbes(data.catalogue)
  useBackendWatch(data.catalogue, onLayersChanged)
  const [aboutOpen, setAboutOpen] = useState(false)
  const sectionId = useView((s) => s.section)
  const full = useView((s) => s.full)
  const placeId = useView((s) => s.place)
  const year = useView((s) => s.year)
  const section = data.catalogue.sections.find((s) => s.id === sectionId) ?? null
  const sectionData = useSectionData(section, placeId, effectiveYear(section?.years, year))
  const place = data.places.find((p) => p.id === (placeId ?? COUNTRY_ID))
  const showCharts = full && section !== null
  return (
    <div className="app">
      <IconRail catalogue={data.catalogue} onAbout={() => setAboutOpen(true)} />
      <SectionPanel data={data} sectionData={sectionData} />
      <main className={showCharts ? 'map-area map-area-full' : 'map-area'}>
        <MapView data={data} />
        {/* In full view the charts take the map's place; the map stays loaded underneath. */}
        {showCharts ? (
          <ChartsView section={section} place={place} sectionData={sectionData} />
        ) : (
          <>
            <div className="map-toolbar">
              <PlaceSearch places={data.places} />
              <Breadcrumb places={data.places} />
            </div>
            <ActiveLayers catalogue={data.catalogue} />
            <Legend catalogue={data.catalogue} />
          </>
        )}
        <TimeSlider catalogue={data.catalogue} />
        <Notices />
      </main>
      <AboutDialog open={aboutOpen} onClose={() => setAboutOpen(false)} />
    </div>
  )
}

export default function App() {
  const { state, retry, refreshCatalogue } = usePortalData()
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
  return <Portal data={state.data} onLayersChanged={refreshCatalogue} />
}
