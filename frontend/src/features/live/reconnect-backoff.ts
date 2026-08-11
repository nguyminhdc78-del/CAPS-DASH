const BASE_DELAY_MS = 1000
const MAX_DELAY_MS = 8000

/**
 * 1s -> 8s exponential backoff with +/-25% jitter.
 *
 * Jitter is not cosmetic: without it, every viewer that got disconnected by
 * the same server restart reconnects at exactly the same moment, turning "the
 * board came back" into a thundering herd against the one board that just
 * came back. `attempt` resets whenever a frame is actually decoded (see
 * `camera-stream-manager.ts`), not merely on socket open - a socket that
 * opens and is immediately policy-closed must not be treated as a success.
 */
export function nextBackoffDelayMs(attempt: number): number {
  const exponential = Math.min(MAX_DELAY_MS, BASE_DELAY_MS * 2 ** attempt)
  const jitter = 0.75 + Math.random() * 0.5
  return Math.round(exponential * jitter)
}
