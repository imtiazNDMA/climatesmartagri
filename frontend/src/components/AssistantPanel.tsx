import { useEffect, useRef, useState, type FormEvent } from 'react'
import { ArrowLeft, ArrowRight, Bot, ChevronRight, Compass, MessageCircle, Send, Sparkles, X } from 'lucide-react'
import { DotLottieReact } from './lottie'
import Markdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import '@fontsource/noto-nastaliq-urdu/arabic-400.css'
import './assistantUrdu.css'
import { askAssistant, fetchAssistantOverview, fetchAssistantTour } from '../api/client'
import type {
  AssistantChatMessage,
  AssistantLanguage,
  AssistantOverview,
  AssistantTour,
  AssistantTourStep,
  StoryCamera,
} from '../api/types'
import type { DistrictRiskState } from '../data/useDistrictRisk'
import { applyPortalActions, useView, viewStore } from '../state/viewState'
import { useAssistantDrag, type AssistantPosition } from './useAssistantDrag'
import { CHAT_TEXT, storedLanguage, storeLanguage } from './assistantLanguage'

type Mode = 'overview' | 'chat' | 'tour'
type ChatEntry = AssistantChatMessage & {
  language: AssistantLanguage
  sources?: string[]
  grounded?: boolean
  uncheckedNumbers?: number[]
}
const TOUR_STEP_MS = 7000

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
  closing,
  onClose,
  onStoryCamera,
  districtRisk,
  position,
  onPositionChange,
}: {
  open: boolean
  closing: boolean
  onClose: () => void
  onStoryCamera: (camera: StoryCamera) => void
  districtRisk: DistrictRiskState
  position: AssistantPosition | null
  onPositionChange: (position: AssistantPosition) => void
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
  const [tourTimer, setTourTimer] = useState(0)
  const [messages, setMessages] = useState<ChatEntry[]>([])
  const [question, setQuestion] = useState('')
  const [busy, setBusy] = useState(false)
  const [language, setLanguage] = useState<AssistantLanguage>(storedLanguage)
  const text = CHAT_TEXT[language]
  const [error, setError] = useState<string | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const closeRef = useRef<HTMLButtonElement>(null)
  const requestRef = useRef<AbortController | null>(null)
  const panelRef = useRef<HTMLElement>(null)
  const panelDrag = useAssistantDrag(panelRef, position, onPositionChange)

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
  useEffect(() => {
    if (!open || mode !== 'tour' || !tour || tourIndex >= tour.steps.length - 1) return
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return
    const timeout = window.setTimeout(() => {
      const next = tourIndex + 1
      setTourIndex(next)
      applyTourStep(tour.steps[next], viewStore.getState().section, onStoryCamera)
    }, TOUR_STEP_MS)
    return () => window.clearTimeout(timeout)
  }, [open, mode, tour, tourIndex, tourTimer, onStoryCamera])

  const currentStep = tour?.steps[tourIndex]
  const startTour = () => {
    setMode('tour')
    setTourIndex(0)
    setTourTimer((timer) => timer + 1)
    if (tour?.steps[0]) applyTourStep(tour.steps[0], section, onStoryCamera)
  }
  const moveTour = (next: number) => {
    if (!tour) return
    const index = Math.max(0, Math.min(tour.steps.length - 1, next))
    setTourIndex(index)
    setTourTimer((timer) => timer + 1)
    applyTourStep(tour.steps[index], viewStore.getState().section, onStoryCamera)
  }
  const submit = async (event: FormEvent) => {
    event.preventDefault()
    const asked = question.trim()
    if (!asked || busy) return
    const history = messages.slice(-8).map(({ role, content }) => ({ role, content }))
    const answerLanguage = language
    setMessages([...messages, { role: 'user', content: asked, language: answerLanguage }])
    setQuestion('')
    setBusy(true)
    setError(null)
    const controller = new AbortController()
    requestRef.current = controller
    try {
      const reply = await askAssistant(asked, history, {
        section_id: section,
        place_id: place,
        year,
        active_layer_ids: layers.filter((layer) => !layer.hidden).map((layer) => layer.id),
        forecast,
        district_risk: districtRisk.status === 'ready' ? {
          hazard: districtRisk.data.hazard,
          statistic: districtRisk.data.statistic.label,
          time: districtRisk.data.time,
          run: districtRisk.data.run,
          districts: districtRisk.data.districts,
        } : null,
      }, controller.signal, answerLanguage)
      if (reply.portal_actions?.length) applyPortalActions(reply.portal_actions)
      setMessages((current) => [...current, {
        role: 'assistant', content: reply.answer, language: answerLanguage, sources: reply.source_names,
        grounded: reply.grounded, uncheckedNumbers: reply.unchecked_numbers,
      }])
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
      ref={panelRef}
      className={`assistant-panel${mode === 'tour' ? ' story-mode' : ''}${position ? ' assistant-positioned' : ''}${closing ? ' assistant-closing' : ''}`}
      role="dialog"
      aria-label="Portal AI assistant"
      style={position ? { left: position.x, top: position.y, right: 'auto', bottom: 'auto' } : undefined}
      onKeyDown={(event) => { if (event.key === 'Escape') onClose() }}
    >
      <header
        className="assistant-header"
        aria-label="Drag portal guide"
        {...panelDrag}
      >
        <span className="assistant-header-icon" aria-hidden="true">
          <DotLottieReact src="/chatbot_header.json" autoplay loop />
        </span>
        <div><strong>Portal guide</strong><small><i />{overview?.local_model === false ? 'AI assistant' : 'Local AI'}</small></div>
        <button
          ref={closeRef}
          type="button"
          aria-label="Close assistant"
          onPointerDown={(event) => event.stopPropagation()}
          onClick={onClose}
        ><X size={18} /></button>
      </header>

      <nav className="assistant-tabs" aria-label="Assistant modes">
        <button type="button" aria-pressed={mode === 'overview'} onClick={() => setMode('overview')}><Sparkles size={15} />Overview</button>
        <button type="button" aria-pressed={mode === 'tour'} onClick={startTour}><Compass size={15} />Tour</button>
        <button type="button" aria-pressed={mode === 'chat'} onClick={() => setMode('chat')}><MessageCircle size={15} />Ask</button>
        {mode === 'chat' && (
          <span className="assistant-language" role="group" aria-label="Answer language">
            {(['en', 'ur'] as const).map((option) => (
              <button
                type="button"
                key={option}
                lang={option}
                aria-pressed={language === option}
                onClick={() => { setLanguage(option); storeLanguage(option) }}
              >{option === 'en' ? 'English' : 'اردو'}</button>
            ))}
          </span>
        )}
      </nav>

      <div className="assistant-body">
        {error && <p className="assistant-error" role="alert">{error}</p>}
        {mode === 'overview' && (
          overview ? (
            <div className="assistant-overview">
              <div className="assistant-overview-intro">
                <h3>Explore the portal</h3>
                <p>Choose a topic to open its map and information.</p>
              </div>
              <div className="assistant-section-list">
                {overview.sections.filter((item) => item.status !== 'coming-soon').map((item) => (
                  <button type="button" key={item.id} onClick={() => { viewStore.getState().openSection(item.id); onClose() }}>
                    <span><strong>{item.title}</strong>{item.summary && <small>{item.summary}</small>}</span>
                    <ChevronRight size={17} aria-hidden />
                  </button>
                ))}
              </div>
              <footer className="assistant-overview-footer">
                <button type="button" className="assistant-primary" onClick={startTour}><Compass size={16} />Start guided tour</button>
                <button type="button" className="assistant-secondary" onClick={() => setMode('chat')}>Ask about this view</button>
              </footer>
            </div>
          ) : <p className="assistant-wait">Loading the portal overview…</p>
        )}

        {mode === 'tour' && (
          currentStep ? (
            <div className="assistant-tour">
              <div className="assistant-tour-meta">
                <span>Story {tourIndex + 1} of {tour?.steps.length}</span>
                <small>{tour && tourIndex < tour.steps.length - 1 ? 'Auto-advancing' : 'Tour complete'}</small>
              </div>
              <h3>{currentStep.title}</h3>
              <p>{currentStep.body}</p>
              <div className="assistant-tour-progress" aria-label={`Tour step ${tourIndex + 1} of ${tour?.steps.length}`}>
                {tour?.steps.map((step, index) => (
                  <i key={step.id} className={index < tourIndex ? 'done' : index === tourIndex ? 'on' : ''} />
                ))}
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
                <div className="assistant-intro" lang={language} dir={language === 'ur' ? 'rtl' : undefined}>
                  <Bot size={24} aria-hidden />
                  <p>{text.intro}</p>
                  {(text.suggestions ?? overview?.suggested_questions ?? []).slice(0, 3).map((suggestion) => (
                    <button type="button" key={suggestion} onClick={() => setQuestion(suggestion)}>{suggestion}</button>
                  ))}
                </div>
              )}
              {messages.map((message, index) => {
                const words = CHAT_TEXT[message.language]
                const dir = message.language === 'ur' ? 'rtl' : undefined
                return (
                  <div key={`${message.role}-${index}`} className={`assistant-message ${message.role}`}>
                    <span lang={message.language}>{message.role === 'user' ? words.you : words.guide}</span>
                    {message.role === 'assistant' ? (
                      <div className="assistant-message-content" lang={message.language} dir={dir}>
                        <Markdown
                          remarkPlugins={[remarkGfm]}
                          allowedElements={['p', 'strong', 'em', 'ul', 'ol', 'li', 'h2', 'h3', 'h4', 'table', 'thead', 'tbody', 'tr', 'th', 'td', 'code', 'blockquote', 'br']}
                        >
                          {message.content}
                        </Markdown>
                      </div>
                    ) : <p lang={message.language} dir="auto">{message.content}</p>}
                    {message.sources && message.sources.length > 0 && (
                      <small lang={message.language} dir={dir}>{words.sources} {message.sources.join(' · ')}</small>
                    )}
                    {message.role === 'assistant' && message.grounded === false && (
                      <small className="assistant-unchecked" role="status" lang={message.language} dir={dir}>
                        {words.unchecked}
                        {message.uncheckedNumbers?.length ? ` ${words.uncheckedList} ${message.uncheckedNumbers.join(', ')}.` : ''}
                      </small>
                    )}
                  </div>
                )
              })}
              {busy && <p className="assistant-thinking" lang={language}><i />{text.thinking}</p>}
            </div>
            <form className="assistant-compose" onSubmit={submit}>
              <input
                ref={inputRef}
                value={question}
                maxLength={2000}
                onChange={(event) => setQuestion(event.target.value)}
                placeholder={text.placeholder}
                aria-label={text.question}
                lang={language}
                dir="auto"
              />
              <button type="submit" aria-label={text.send} disabled={!question.trim() || busy}><Send size={17} /></button>
            </form>
          </div>
        )}
      </div>
    </aside>
  )
}
