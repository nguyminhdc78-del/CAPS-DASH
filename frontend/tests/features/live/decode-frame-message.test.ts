import { describe, expect, it } from 'vitest'

import { decodeFrameMessage } from '@/features/live/decode-frame-message'

const HEADER_LENGTH_BYTES = 4

/**
 * Mirrors backend/caps_dash/realtime/frame_protocol.py::encode_frame_message
 * byte for byte, so this fixture is what the server actually puts on the
 * wire - not a shape this test invented independently of it.
 */
function encodeFixture(header: unknown, jpeg: Uint8Array): ArrayBuffer {
  const headerBytes = new TextEncoder().encode(JSON.stringify(header))
  const message = new Uint8Array(HEADER_LENGTH_BYTES + headerBytes.length + jpeg.length)
  new DataView(message.buffer).setUint32(0, headerBytes.length, false)
  message.set(headerBytes, HEADER_LENGTH_BYTES)
  message.set(jpeg, HEADER_LENGTH_BYTES + headerBytes.length)
  return message.buffer
}

describe('decodeFrameMessage', () => {
  it('round-trips a header and JPEG bytes', async () => {
    const header = { camera_id: 1, camera_code: 'CAM-1', seq: 42, frame_w: 640, frame_h: 480 }
    const jpeg = new Uint8Array([0xff, 0xd8, 0x00, 0x01, 0xff, 0xd9])

    const decoded = decodeFrameMessage(encodeFixture(header, jpeg))

    expect(decoded.header).toEqual(header)
    expect(decoded.jpeg.type).toBe('image/jpeg')
    const bytes = new Uint8Array(await decoded.jpeg.arrayBuffer())
    expect(Array.from(bytes)).toEqual(Array.from(jpeg))
  })

  it('rejects a message shorter than the 4-byte length prefix', () => {
    const tooShort = new Uint8Array([0, 0, 1]).buffer
    expect(() => decodeFrameMessage(tooShort)).toThrow(/truncated/)
  })

  it('rejects a declared header length that runs past the end of the buffer', () => {
    const buffer = new Uint8Array(8)
    new DataView(buffer.buffer).setUint32(0, 100, false) // claims 100 bytes, only 4 remain
    expect(() => decodeFrameMessage(buffer.buffer)).toThrow(/out of range/)
  })

  it('rejects a declared header length past the 1 MiB cap', () => {
    const buffer = new Uint8Array(8)
    new DataView(buffer.buffer).setUint32(0, (1 << 20) + 1, false)
    expect(() => decodeFrameMessage(buffer.buffer)).toThrow(/out of range/)
  })
})
