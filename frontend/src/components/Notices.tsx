import { X } from 'lucide-react'
import { fetchHealth } from '../api/client'
import { uiStore, useUi } from '../state/uiState'

export function Notices() {
  const notices = useUi((s) => s.notices)
  const backendLost = useUi((s) => s.backendLost)

  const recheck = () => {
    fetchHealth()
      .then(() => uiStore.getState().setBackendLost(false))
      .catch(() => undefined)
  }

  if (!notices.length && !backendLost) return null
  return (
    <div className="notices" role="status">
      {backendLost && (
        <div className="notice notice-warning">
          <span>The portal has lost its data service. What is on screen is unchanged.</span>
          <button type="button" onClick={recheck}>
            Check again
          </button>
        </div>
      )}
      {notices.map((notice) => (
        <div className="notice" key={notice.id}>
          <span>{notice.text}</span>
          <button
            type="button"
            aria-label="Dismiss notice"
            onClick={() => uiStore.getState().dismissNotice(notice.id)}
          >
            <X size={14} />
          </button>
        </div>
      ))}
    </div>
  )
}
