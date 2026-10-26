import { useEffect, useRef, type PointerEvent as ReactPointerEvent, type RefObject } from 'react'

export type AssistantPosition = { x: number; y: number }

// Leave enough room for borders, fractional layout pixels and the panel shadow at viewport edges.
const EDGE_GAP = 12

export function clampAssistantPosition(position: AssistantPosition, width: number, height: number): AssistantPosition {
  return {
    x: Math.max(EDGE_GAP, Math.min(position.x, window.innerWidth - width - EDGE_GAP)),
    y: Math.max(EDGE_GAP, Math.min(position.y, window.innerHeight - height - EDGE_GAP)),
  }
}

export function useAssistantDrag(
  ref: RefObject<HTMLElement | null>,
  position: AssistantPosition | null,
  onPositionChange: (position: AssistantPosition) => void,
) {
  const drag = useRef<{ pointerId: number; dx: number; dy: number; moved: boolean } | null>(null)
  const suppressClick = useRef(false)

  useEffect(() => {
    const keepOnScreen = () => {
      const node = ref.current
      if (!node || !position) return
      const bounds = node.getBoundingClientRect()
      const next = clampAssistantPosition(position, bounds.width, bounds.height)
      if (next.x !== position.x || next.y !== position.y) onPositionChange(next)
    }
    window.addEventListener('resize', keepOnScreen)
    keepOnScreen()
    return () => window.removeEventListener('resize', keepOnScreen)
  }, [onPositionChange, position, ref])

  const onPointerDown = (event: ReactPointerEvent<HTMLElement>) => {
    if (event.button !== 0) return
    const node = ref.current
    if (!node) return
    const bounds = node.getBoundingClientRect()
    drag.current = { pointerId: event.pointerId, dx: event.clientX - bounds.left, dy: event.clientY - bounds.top, moved: false }
    event.currentTarget.setPointerCapture(event.pointerId)
  }
  const onPointerMove = (event: ReactPointerEvent<HTMLElement>) => {
    const current = drag.current
    const node = ref.current
    if (!current || !node || current.pointerId !== event.pointerId) return
    const bounds = node.getBoundingClientRect()
    const next = clampAssistantPosition(
      { x: event.clientX - current.dx, y: event.clientY - current.dy },
      bounds.width,
      bounds.height,
    )
    if (Math.abs(event.movementX) + Math.abs(event.movementY) > 2) current.moved = true
    onPositionChange(next)
  }
  const finishDrag = (event: ReactPointerEvent<HTMLElement>) => {
    if (drag.current?.pointerId !== event.pointerId) return
    suppressClick.current = drag.current.moved
    drag.current = null
    event.currentTarget.releasePointerCapture(event.pointerId)
  }
  const onClickCapture = (event: React.MouseEvent<HTMLElement>) => {
    if (!suppressClick.current) return
    suppressClick.current = false
    event.preventDefault()
    event.stopPropagation()
  }

  return { onPointerDown, onPointerMove, onPointerUp: finishDrag, onPointerCancel: finishDrag, onClickCapture }
}
