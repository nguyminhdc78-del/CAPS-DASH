import type { SlotState } from '@/shared/components/state-tag'

/**
 * One slot's overlay data for the frame just received.
 *
 * `polygon` is already fitted to this frame's pixel grid by the backend (see
 * `frame_header.py`) - the client only has to scale it to the display box, it
 * never has to know about the ROI editor's source-pixel coordinate space.
 */
export interface SlotOverlay {
  code: string
  state: SlotState
  polygon: [number, number][]
}

export interface DetectionBox {
  x1: number
  y1: number
  x2: number
  y2: number
  confidence: number
  label: string
}

/**
 * The JSON half of one realtime message. Mirrors
 * `backend/caps_dash/realtime/frame_header.py::build_frame_header` field for
 * field - keep the two in sync by hand, there is no shared schema generator
 * for the WS payloads (unlike the REST API's openapi-typescript pipeline).
 */
export interface FrameHeader {
  camera_id: number
  camera_code: string
  seq: number
  captured_at: string
  frame_w: number
  frame_h: number
  process_ms: number
  confidence: number
  slots: SlotOverlay[]
  detections: DetectionBox[]
}
