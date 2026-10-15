import { useEffect, useRef, useState, type FormEvent } from 'react'
import { ArrowLeft, ArrowRight, Bot, Compass, MessageCircle, Send, Sparkles, X } from 'lucide-react'
import { askAssistant, fetchAssistantOverview, fetchAssistantTour } from '../api/client'
import type {
  AssistantChatMessage,
  AssistantOverview,
  AssistantTour,
  AssistantTourStep,
  StoryCamera,
} from '../api/types'
import type { DistrictRiskState } from '../data/useDistrictRisk'
import { useView, viewStore } from '../state/viewState'

type Mode = 'overview' | 'chat' | 'tour'
type ChatEntry = AssistantChatMessage & { sources?: string[] }

function applyTourStep(
  step: AssistantTourStep,
  openSection: string | null,
  onStoryCamera: (camera: StoryCamera) => void,
) {
  onStoryCamera(step.camera)
  if (step.action?.type === 'open-section' && openSection !== step.action.section_id) {
    viewStore.getState().openSection(step.action.section_id)
  }
}

export function AssistantPanel({
  open,
  onClose,
  onStoryCamera,
  districtRisk,
}: {
  open: boolean
  onClose: () => void
  onStoryCamera: (camera: StoryCamera) => void
  districtRisk: DistrictRiskState
}) {
  const section = useView((state) => state.section)
  const place = useView((state) => state.place)
  const year = useView((state) => state.year)
  const layers = useView((state) => state.layers)
  const forecast = useView((state) => state.forecast)
  const [mode, setMode] = useState<Mode>('overview')
  const [overview, setOverview] = useState<AssistantOverview | null>(null)
  const [tour, setTour] = useState<AssistantTour | null>(null)
  const [tourIndex, setTourIndex] = useState(0)
  const [messages, setMessages] = useState<ChatEntry[]>([])
  const [question, setQuestion] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const closeRef = useRef<HTMLButtonElement>(null)
  const requestRef = useRef<AbortController | null>(null)

  useEffect(() => {
    if (!open || overview) return
    let cancelled = false
    Promise.all([fetchAssistantOverview(), fetchAssistantTour()])
      .then(([nextOverview, nextTour]) => {
        if (!cancelled) {
          setOverview(nextOverview)
          setTour(nextTour)
        }
      })
      .catch((problem: unknown) => {
        if (!cancelled) setError(problem instanceof Error ? problem.message : String(problem))
      })
    return () => { cancelled = true }
  }, [open, overview])

  useEffect(() => {
    if (open && mode === 'chat') inputRef.current?.focus()
  }, [open, mode])
  useEffect(() => {
    if (open) closeRef.current?.focus()
    else requestRef.current?.abort()
  }, [open])

  if (!open) return null

  const currentStep = tour?.steps[tourIndex]
  const startTour = () => {
    setMode('tour')
    setTourIndex(0)
    if (tour?.steps[0]) applyTourStep(tour.steps[0], section, onStoryCamera)
  }
  const moveTour = (next: number) => {
    if (!tour) return
    const index = Math.max(0, Math.min(tour.steps.length - 1, next))
    setTourIndex(index)
    applyTourStep(tour.steps[index], viewStore.getState().section, onStoryCamera)
  }
  const submit = async (event: FormEvent) => {
    event.preventDefault()
    const text = question.trim()
    if (!text || busy) return
    const history = messages.slice(-8).map(({ role, content }) => ({ role, content }))
    setMessages([...messages, { role: 'user', content: text }])
    setQuestion('')
    setBusy(true)
    setError(null)
    const controller = new AbortController()
    requestRef.current = controller
    try {
      const reply = await askAssistant(text, history, {
        section_id: section,
        place_id: place,
        year,
        active_layer_ids: layers.filter((layer) => !layer.hidden).map((layer) => layer.id),
        forecast,
        district_risk: districtRisk.status === 'ready' ? {
          hazard: districtRisk.data.hazard,
          statistic: districtRisk.data.statistic.label,
          districts: districtRisk.data.districts,
        } : null,
      }, controller.signal)
      setMessages((current) => [...current, { role: 'assistant', content: reply.answer, sources: reply.sources }])
    } catch (problem) {
      setMessages((current) => current.slice(0, -1))
      if (!(problem instanceof DOMException && problem.name === 'AbortError')) {
        setError(problem instanceof Error ? problem.message : String(problem))
      }
    } finally {
      if (requestRef.current === controller) requestRef.current = null
      setBusy(false)
    }
  }

  return (
    <aside
      className={`assistant-panel${mode === 'tour' ? ' story-mode' : ''}`}
      role="dialog"
      aria-label="Portal AI assistant"
      onKeyDown={(event) => { if (event.key === 'Escape') onClose() }}
    >
      <header className="assistant-header">
        <span><Bot size={22} aria-hidden /></span>
        <div><strong>Portal guide</strong><small>{overview ? `${overview.local_model ? 'Local ' : ''}${overview.model}` : 'Qwen'}</small></div>
        <button ref={closeRef} type="button" aria-label="Close assistant" onClick={onClose}><X size={18} /></button>
      </header>

      <nav className="assistant-tabs" aria-label="Assistant modes">
        <button type="button" aria-pressed={mode === 'overview'} onClick={() => setMode('overview')}><Sparkles size={15} />Overview</button>
        <button type="button" aria-pressed={mode === 'tour'} onClick={startTour}><Compass size={15} />Tour</button>
        <button type="button" aria-pressed={mode === 'chat'} onClick={() => setMode('chat')}><MessageCircle size={15} />Ask</button>
      </nav>

      <div className="assistant-body">
        {error && <p className="assistant-error" role="alert">{error}</p>}
        {mode === 'overview' && (
          overview ? (
            <div className="assistant-overview">
              <p>{overview.summary}</p>
              <h3>Explore the portal</h3>
              <div className="assistant-section-list">
                {overview.sections.filter((item) => item.status !== 'coming-soon').map((item) => (
                  <button type="button" key={item.id} onClick={() => viewStore.getState().openSection(item.id)}>
                    <strong>{item.title}</strong><span>{item.summary || 'Open this section to explore its maps and information.'}</span>
                  </button>
                ))}
              </div>
              <button type="button" className="assistant-primary" onClick={startTour}><Compass size={16} />Start guided tour</button>
            </div>
          ) : <p className="assistant-wait">Loading the portal overview…</p>
        )}

        {mode === 'tour' && (
          currentStep ? (
            <div className="assistant-tour">
              <span>Story {tourIndex + 1} of {tour?.steps.length}</span>
              <h3>{currentStep.title}</h3>
              <p>{currentStep.body}</p>
              <div className="assistant-tour-progress" aria-hidden>
                {tour?.steps.map((step, index) => <i key={step.id} className={index === tourIndex ? 'on' : ''} />)}
              </div>
              <div className="assistant-tour-actions">
                <button type="button" disabled={tourIndex === 0} onClick={() => moveTour(tourIndex - 1)}><ArrowLeft size={16} />Back</button>
                {tour && tourIndex < tour.steps.length - 1 ? (
                  <button type="button" className="assistant-primary" onClick={() => moveTour(tourIndex + 1)}>Next<ArrowRight size={16} /></button>
                ) : (
                  <button type="button" className="assistant-primary" onClick={() => setMode('chat')}>Ask a question</button>
                )}
              </div>
            </div>
          ) : <p className="assistant-wait">Loading the guided tour…</p>
        )}

        {mode === 'chat' && (
          <div className="assistant-chat">
            <div className="assistant-messages" aria-live="polite">
              {messages.length === 0 && (
                <div className="assistant-intro">
                  <Bot size={24} aria-hidden />
                  <p>Ask about the current map, a portal section, indicators, forecasts, or hazard guidance.</p>
                  {overview?.suggested_questions.slice(0, 3).map((suggestion) => (
                    <button type="button" key={suggestion} onClick={() => setQuestion(suggestion)}>{suggestion}</button>
                  ))}
                </div>
              )}
              {messages.map((message, index) => (
                <div key={`${message.role}-${index}`} className={`assistant-message ${message.role}`}>
                  <span>{message.role === 'user' ? 'You' : 'Guide'}</span>
                  <p>{message.content}</p>
                  {message.sources && message.sources.length > 0 && (
                    <small>Sources: {message.sources.join(' · ')}</small>
                  )}
                </div>
              ))}
              {busy && <p className="assistant-thinking"><i />Qwen is thinking…</p>}
            </div>
            <form className="assistant-compose" onSubmit={submit}>
              <input
                ref={inputRef}
                value={question}
                maxLength={2000}
                onChange={(event) => setQuestion(event.target.value)}
                placeholder="Ask about this portal…"
                aria-label="Question for the portal guide"
              />
              <button type="submit" aria-label="Send question" disabled={!question.trim() || busy}><Send size={17} /></button>
            </form>
            <small className="assistant-disclaimer">Answers come from a local AI model and may be inaccurate. Verify important decisions.</small>
          </div>
        )}
      </div>
    </aside>
  )
}
