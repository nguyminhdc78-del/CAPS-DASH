import { useEffect, useState } from 'react'

/**
 * Delays reflecting `value` until it has stopped changing for `delayMs`.
 *
 * Built for the camera confidence slider: dragging fires dozens of onChange
 * events a second, and without this every one of them would queue a PATCH.
 * The debounced value is what triggers the network call; callers keep using
 * the raw, un-debounced value to drive the control itself so the handle
 * never visibly lags behind the pointer.
 */
export function useDebouncedValue<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value)

  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delayMs)
    return () => clearTimeout(timer)
  }, [value, delayMs])

  return debounced
}
