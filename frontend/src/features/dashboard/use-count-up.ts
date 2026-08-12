import { useEffect, useRef, useState } from 'react'

const ANIMATION_MS = 500

/**
 * Interpolates the displayed number from its previous value to `value`
 * whenever `value` changes, so a jump in a headline counter reads as motion
 * instead of a silent tick. This never invents an intermediate value that
 * did not come from the API - it only smooths the transition between two
 * numbers that both genuinely arrived from `/summary`.
 *
 * Skips the animation (jumps straight to `value`) for `prefers-reduced-
 * motion` and for environments with no `requestAnimationFrame` - the same
 * defensive pattern `camera-stream-view.tsx` uses for `ResizeObserver`,
 * which jsdom (the unit tests) does not implement either.
 */
export function useCountUp(value: number): number {
  const [display, setDisplay] = useState(value)
  const fromRef = useRef(value)

  useEffect(() => {
    const canAnimate =
      typeof window !== 'undefined' &&
      typeof window.requestAnimationFrame === 'function' &&
      !window.matchMedia('(prefers-reduced-motion: reduce)').matches

    if (!canAnimate || value === fromRef.current) {
      fromRef.current = value
      setDisplay(value)
      return undefined
    }

    const from = fromRef.current
    const start = performance.now()
    // Reads `performance.now()` itself on every tick rather than trusting
    // the timestamp `requestAnimationFrame` hands the callback: jsdom's rAF
    // implementation does not guarantee that argument shares an epoch with
    // `performance.now()`, which produced wildly negative "progress" (and
    // therefore out-of-range displayed numbers) under the unit tests. Real
    // browsers give both the same clock, so this is a no-op there.
    let frame = requestAnimationFrame(function tick() {
      const progress = Math.min(1, Math.max(0, (performance.now() - start) / ANIMATION_MS))
      setDisplay(Math.round(from + (value - from) * progress))
      if (progress < 1) {
        frame = requestAnimationFrame(tick)
      } else {
        fromRef.current = value
      }
    })

    return () => cancelAnimationFrame(frame)
  }, [value])

  return display
}
