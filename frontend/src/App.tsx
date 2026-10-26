import { useEffect, useRef, useState } from 'react'
import { DotLottieReact } from './components/lottie'
import { AboutDialog } from './components/AboutDialog'
import { AssistantPanel } from './components/AssistantPanel'
import { ActiveLayers } from './components/ActiveLayers'
import { BackendDown } from './components/BackendDown'
import { ForecastSlider } from './components/ForecastSlider'
import { ChartsView } from './components/ChartsView'
import { Breadcrumb } from './components/Breadcrumb'
import { BasemapSelector } from './components/BasemapSelector'
import { IconRail } from './components/IconRail'
import { Legend } from './components/Legend'
import { MapView } from './components/MapView'
import { Notices } from './components/Notices'
import { PlaceSearch } from './components/PlaceSearch'
import { SectionPanel } from './components/SectionPanel'
import { TimeSlider } from './components/TimeSlider'
import { TitleBar } from './components/TitleBar'
import { useAssistantDrag, type AssistantPosition } from './components/useAssistantDrag'
import Switch from './components/ui/sky-toggle'
import { useBackendWatch } from './data/useBackendWatch'
import { useForecastTimes } from './data/useForecastTimes'
import { useDistrictRisk } from './data/useDistrictRisk'
import { useLayerProbes } from './data/useLayerProbes'
import { useHazardProducts } from './data/useHazardProducts'
import { usePortalData, type PortalData } from './data/usePortalData'
import { useSectionData } from './data/useSectionData'
import { COUNTRY_ID, type StoryCamera } from './api/types'
import { effectiveYear } from './state/selectors'
import type { BasemapId } from './map/basemaps'
import { useView } from './state/viewState'
import { useUrlSync } from './state/useUrlSync'

function Portal({ data, onLayersChanged }: { data: PortalData; onLayersChanged: () => void }) {
  useUrlSync(data.catalogue, data.places)
  useLayerProbes(data.catalogue)
  useBackendWatch(data.catalogue, onLayersChanged)
  const [aboutOpen, setAboutOpen] = useState(false)
  const [assistantOpen, setAssistantOpen] = useState(false)
  const [assistantMounted, setAssistantMounted] = useState(false)
  const [assistantClosing, setAssistantClosing] = useState(false)
  const [assistantPosition, setAssistantPosition] = useState<AssistantPosition | null>(null)
  const launcherRef = useRef<HTMLButtonElement>(null)
  const launcherDrag = useAssistantDrag(launcherRef, assistantPosition, setAssistantPosition)
  const openAssistant = () => {
    setAssistantClosing(false)
    setAssistantMounted(true)
    setAssistantOpen(true)
  }
  const closeAssistant = () => {
    setAssistantOpen(false)
    setAssistantClosing(true)
  }
  useEffect(() => {
    if (!assistantClosing) return
    const duration = window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 0 : 160
    const timeout = window.setTimeout(() => {
      setAssistantMounted(false)
      setAssistantClosing(false)
    }, duration)
    return () => window.clearTimeout(timeout)
  }, [assistantClosing])
  const [storyCamera, setStoryCamera] = useState<StoryCamera | null>(null)
  const [darkMode, setDarkMode] = useState(() => {
    const saved = localStorage.getItem('csa-theme')
    return saved ? saved === 'dark' : window.matchMedia('(prefers-color-scheme: dark)').matches
  })
  const [basemap, setBasemap] = useState<BasemapId>(() =>
    (localStorage.getItem('csa-basemap') as BasemapId | null) ?? 'positron')
  useEffect(() => {
    document.documentElement.dataset.theme = darkMode ? 'dark' : 'light'
    document.documentElement.style.colorScheme = darkMode ? 'dark' : 'light'
    localStorage.setItem('csa-theme', darkMode ? 'dark' : 'light')
  }, [darkMode])
  useEffect(() => localStorage.setItem('csa-basemap', basemap), [basemap])
  const sectionId = useView((s) => s.section)
  const full = useView((s) => s.full)
  const placeId = useView((s) => s.place)
  const year = useView((s) => s.year)
  const section = data.catalogue.sections.find((s) => s.id === sectionId) ?? null
  const hazardProducts = useHazardProducts(section?.kind === 'hazards')
  // A forecast section has no figures or charts of its own to ask for.
  const sectionData = useSectionData(
    section?.kind === 'forecast' || section?.kind === 'crop-classification' || section?.kind === 'hazards' ? null : section,
    placeId,
    effectiveYear(section?.years, year),
  )
  const forecastTimes = useForecastTimes()
  const districtRisk = useDistrictRisk(section?.kind === 'hazards', hazardProducts, forecastTimes)
  const place = data.places.find((p) => p.id === (placeId ?? COUNTRY_ID))
  const showCharts = full && section !== null && section.kind !== 'crop-classification'
  return (
    <div className="app">
      <TitleBar />
      <div className="app-body">
        <IconRail
          catalogue={data.catalogue}
          onAbout={() => setAboutOpen(true)}
        />
        <SectionPanel
          data={data}
          sectionData={sectionData}
          forecastTimes={forecastTimes}
          hazardProducts={hazardProducts}
          districtRisk={districtRisk}
        />
        <main className={showCharts ? 'map-area map-area-full' : 'map-area'}>
          <MapView
            data={data}
            darkMode={darkMode}
            basemap={basemap}
            forecastTimes={forecastTimes}
            districtRisk={districtRisk}
            storyCamera={storyCamera}
          />
          {/* In full view the charts take the map's place; the map stays loaded underneath. */}
          {showCharts ? (
            <ChartsView section={section} place={place} sectionData={sectionData} />
          ) : (
            <>
              <div className="map-toolbar">
                <PlaceSearch places={data.places} />
                <div className="map-toolbar-actions">
                  <BasemapSelector value={basemap} onChange={setBasemap} />
                  <div className="map-theme-toggle">
                    <Switch checked={darkMode} onChange={setDarkMode} />
                  </div>
                  <Breadcrumb places={data.places} />
                </div>
              </div>
              <ActiveLayers catalogue={data.catalogue} />
              <Legend catalogue={data.catalogue} />
            </>
          )}
          {section?.kind !== 'forecast' && section?.kind !== 'crop-classification' && section?.kind !== 'hazards' && <TimeSlider catalogue={data.catalogue} />}
          {!showCharts && <ForecastSlider times={forecastTimes} />}
          <Notices />
        </main>
      </div>
      {!assistantMounted && (
        <button
          ref={launcherRef}
          type="button"
          className="assistant-launcher"
          aria-label="AI portal guide"
          title="AI portal guide"
          style={assistantPosition ? { left: assistantPosition.x, top: assistantPosition.y, right: 'auto', bottom: 'auto' } : undefined}
          {...launcherDrag}
          onClick={openAssistant}
        >
          <span className="assistant-launcher-icon" aria-hidden="true">
            <DotLottieReact
              src="/chatbot_header.json"
              autoplay
              loop
            />
          </span>
          <span className="assistant-launcher-copy">
            <strong>Portal guide</strong>
            <small>Ask about this map</small>
          </span>
        </button>
      )}
      <AboutDialog open={aboutOpen} onClose={() => setAboutOpen(false)} />
      {assistantMounted && (
        <AssistantPanel
          open={assistantOpen}
          closing={assistantClosing}
          onClose={closeAssistant}
          onStoryCamera={(camera) => setStoryCamera({ ...camera })}
          districtRisk={districtRisk}
          position={assistantPosition}
          onPositionChange={setAssistantPosition}
        />
      )}
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
