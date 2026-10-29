import { animate, createTimeline, stagger } from 'animejs'

/**
 * The card deck's motion that needs more than a CSS transition. Each piece answers something the reader
 * just did, is over within half a second, and is skipped altogether for a reader who has asked for less motion.
 */

export const motionOk = () => !window.matchMedia('(prefers-reduced-motion: reduce)').matches

/** Draw the scale in: the bar grows from its low end, then the values settle under it one after another. */
export function drawGauge(gauge: HTMLElement): void {
  if (!motionOk()) return
  const bar = gauge.querySelector('.deck-gauge-bar')
  const ticks = gauge.querySelectorAll('.deck-gauge-ticks span')
  if (!bar) return
  createTimeline({ defaults: { ease: 'outCubic' } })
    .add(bar, { scaleX: [0, 1], duration: 460 })
    .add(ticks, { opacity: [0, 1], translateY: [-5, 0], duration: 240, delay: stagger(45) }, 170)
}

/**
 * Carry a card's picture up into the banner: a copy of it travels from where the card was to where the
 * banner's picture is, growing to fit, and fades as the banner itself appears beneath it.
 */
export function flyArt(from: DOMRect, to: HTMLElement, backgroundImage: string): void {
  if (!motionOk()) return
  const target = to.getBoundingClientRect()
  const ghost = document.createElement('div')
  Object.assign(ghost.style, {
    position: 'fixed', zIndex: '1000', pointerEvents: 'none', backgroundImage, backgroundSize: 'cover',
    left: `${from.left}px`, top: `${from.top}px`, width: `${from.width}px`, height: `${from.height}px`,
    borderRadius: '9px', boxShadow: '0 14px 30px -12px rgb(12 26 46 / 45%)',
  })
  document.body.appendChild(ghost)
  createTimeline({ onComplete: () => ghost.remove() })
    .add(ghost, {
      left: target.left, top: target.top, width: target.width, height: target.height, borderRadius: 20,
      duration: 420, ease: 'outExpo',
    })
    .add(ghost, { opacity: 0, duration: 180, ease: 'linear' }, 300)
}

/**
 * Run a number from 0 to 1 over a short while, calling back with it on the way and with exactly 1 at the
 * end. Returns a function that stops it early. With motion off it calls back once, with 1.
 */
export function runShare(onShare: (share: number) => void, duration = 360): () => void {
  if (!motionOk()) {
    onShare(1)
    return () => {}
  }
  const state = { share: 0 }
  const running = animate(state, {
    share: 1, duration, ease: 'outCubic',
    onUpdate: () => onShare(state.share),
    onComplete: () => onShare(1),
  })
  return () => {
    running.cancel()
  }
}
