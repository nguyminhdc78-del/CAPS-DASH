export type CloseAction = 'refresh-and-reconnect' | 'reconnect-with-backoff' | 'no-retry'

/** The subset of `CloseEvent` this module actually reads - easy to fake in tests. */
export interface StreamCloseInfo {
  code: number
  reason: string
}

/**
 * What to do after the socket closes, from the code + reason alone.
 *
 * Mirrors `backend/caps_dash/realtime/close_codes.py`:
 *   1008 token_expired         -> the credential, not the network, failed: refresh and reconnect at once
 *   1008 (anything else)       -> forbidden / auth_invalid / auth_timeout / camera_unknown: policy, never retry
 *   1013 too_many_viewers      -> the viewer cap is full; retrying silently just re-queues behind it - manual retry only
 *   1000                       -> our own clean close (unmount, tab hidden, freeze) - nothing to recover from
 *   everything else            -> 1001 heartbeat_lost, 1006 abnormal closure, 1011 internal error: transient, back off and retry
 */
export function classifyClose(event: StreamCloseInfo): CloseAction {
  if (event.code === 1008) {
    return event.reason === 'token_expired' ? 'refresh-and-reconnect' : 'no-retry'
  }
  if (event.code === 1013 || event.code === 1000) return 'no-retry'
  return 'reconnect-with-backoff'
}
