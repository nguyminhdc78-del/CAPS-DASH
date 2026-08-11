/**
 * Control messages are tiny textual JSON. The only inbound one this client
 * acts on is the server's heartbeat ping (reply `pong` or get dropped after
 * two misses) - `auth_ok` needs no reaction, and anything unrecognised is
 * ignored rather than trusted.
 */
export function isPingMessage(raw: string): boolean {
  try {
    const message: unknown = JSON.parse(raw)
    return (
      typeof message === 'object' && message !== null && (message as { type?: unknown }).type === 'ping'
    )
  } catch {
    return false
  }
}
