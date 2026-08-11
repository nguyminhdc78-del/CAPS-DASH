/**
 * Source-frame pixels <-> display-box pixels. THE critical module of this
 * feature - see phase-11 plan §"Coordinate transform".
 *
 * A parking slot's shape is persisted as `points` in SOURCE-FRAME pixels
 * (the camera's actual frame width/height at draw time), never in whatever
 * size the browser happened to render the still at. The editor converts at
 * the Konva boundary only: reducer state stays in source pixels end to end.
 *
 * Every conversion here uses INDEPENDENT x and y factors
 * (`display.width / source.width`, `display.height / source.height`
 * separately) and NEVER a single shared `scale` (e.g. `Math.min(scaleX,
 * scaleY)`). The reason this is load-bearing, not stylistic: a shared factor
 * only produces the right answer when the display box happens to share the
 * source's aspect ratio exactly. The moment it does not - a browser window
 * resized to an odd ratio, or (worse) a camera whose resolution changed
 * between when a slot was drawn and when the page reloads the current
 * snapshot - a shared factor silently stretches one axis more than the
 * other. Every polygon then sits a few pixels off from the cars it should
 * outline, ray-casting quietly stops matching detections inside them, and
 * every slot behind that camera reports FREE forever with nothing raised
 * anywhere - the exact silent failure this whole phase exists to prevent.
 * Independent per-axis factors are correct regardless of aspect ratio, so
 * the bug class cannot occur, not merely "usually does not occur".
 */

export interface Point {
  x: number
  y: number
}

export interface FrameSize {
  width: number
  height: number
}

/**
 * The one place both directions' math lives. `sourceToDisplay` and
 * `displayToSource` are thin, named wrappers around this so call sites read
 * as intent ("convert this drawn point for saving") rather than "which way
 * round do I divide" - a wrapper misuse is a one-line diff to spot in review,
 * an inlined division the wrong way round is not.
 */
function scalePoint(point: Point, from: FrameSize, to: FrameSize): Point {
  return {
    x: point.x * (to.width / from.width),
    y: point.y * (to.height / from.height),
  }
}

/** Source-frame pixels -> display pixels. Independent axis factors, always. */
export function sourceToDisplay(point: Point, source: FrameSize, display: FrameSize): Point {
  return scalePoint(point, source, display)
}

/** Display pixels -> source-frame pixels. Inverse of the above, same independence. */
export function displayToSource(point: Point, source: FrameSize, display: FrameSize): Point {
  return scalePoint(point, display, source)
}

/**
 * Reproject a point drawn against one frame size onto another frame size.
 *
 * Reuses the exact same per-axis math as sourceToDisplay/displayToSource
 * (scaling by a to/from pixel ratio is the same operation regardless of
 * which two frames are involved) to handle the case where a camera's
 * resolution changed between when a slot map was drawn and the snapshot the
 * editor just loaded. See `use-roi-editor-data.ts`.
 */
export function rescaleToFrame(point: Point, from: FrameSize, to: FrameSize): Point {
  return scalePoint(point, from, to)
}

/** Keeps a vertex inside the source frame while dragging. */
export function clampToFrame(point: Point, frame: FrameSize): Point {
  return {
    x: Math.min(Math.max(point.x, 0), frame.width),
    y: Math.min(Math.max(point.y, 0), frame.height),
  }
}
