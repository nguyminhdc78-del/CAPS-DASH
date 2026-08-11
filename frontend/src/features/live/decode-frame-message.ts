import type { FrameHeader } from './frame-header-types'

const HEADER_LENGTH_BYTES = 4

// A guard against a corrupted or hostile message, not a claim about what the
// server actually sends (see backend/caps_dash/realtime/frame_protocol.py for
// its own, tighter limit). Rejecting early avoids allocating a huge Uint8Array
// for a length field that was never real.
const MAX_HEADER_BYTES = 1 << 20

export interface DecodedFrameMessage {
  header: FrameHeader
  jpeg: Blob
}

/**
 * Client half of the realtime wire format:
 *
 *   [4 bytes big-endian uint32 = header length N][N bytes UTF-8 JSON][JPEG bytes]
 *
 * Deliberately the mirror image of the server's `decode_frame_message` in
 * `frame_protocol.py` - same three guards, same order, so a fixture built for
 * one codec's test is valid input for the other.
 */
export function decodeFrameMessage(buffer: ArrayBuffer): DecodedFrameMessage {
  if (buffer.byteLength < HEADER_LENGTH_BYTES) {
    throw new Error('frame message truncated')
  }

  // `false` = big-endian, matching Python's `int.from_bytes(..., "big")`.
  const headerLength = new DataView(buffer).getUint32(0, false)
  const end = HEADER_LENGTH_BYTES + headerLength
  if (headerLength > MAX_HEADER_BYTES || end > buffer.byteLength) {
    throw new Error('frame header length out of range')
  }

  const headerText = new TextDecoder().decode(
    new Uint8Array(buffer, HEADER_LENGTH_BYTES, headerLength),
  )
  const header = JSON.parse(headerText) as FrameHeader
  const jpeg = new Blob([new Uint8Array(buffer, end)], { type: 'image/jpeg' })
  return { header, jpeg }
}
