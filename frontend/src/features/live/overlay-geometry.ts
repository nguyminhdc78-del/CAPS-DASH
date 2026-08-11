export interface DisplayRect {
  left: number
  top: number
  width: number
  height: number
}

/**
 * The rectangle `object-fit: contain` actually paints inside a `boxWidth x
 * boxHeight` box, given the image's own natural pixel size.
 *
 * The overlay canvas is sized and positioned to exactly this rectangle - not
 * the box - so a coordinate mapped through it lands on the pixel the camera
 * actually reported, letterboxing included. Returns null while there is
 * nothing to measure yet (no image loaded, or a zero-size container mid-layout).
 */
export function computeContainedRect(
  boxWidth: number,
  boxHeight: number,
  naturalWidth: number,
  naturalHeight: number,
): DisplayRect | null {
  if (boxWidth <= 0 || boxHeight <= 0 || naturalWidth <= 0 || naturalHeight <= 0) return null

  const boxRatio = boxWidth / boxHeight
  const naturalRatio = naturalWidth / naturalHeight
  const fitsToWidth = naturalRatio > boxRatio

  const width = fitsToWidth ? boxWidth : boxHeight * naturalRatio
  const height = fitsToWidth ? boxWidth / naturalRatio : boxHeight

  return { left: (boxWidth - width) / 2, top: (boxHeight - height) / 2, width, height }
}

/**
 * Frame-pixel -> display-pixel scale, with INDEPENDENT x and y factors.
 *
 * A single shared scale is only correct when `frame_w`/`frame_h` happen to
 * match the rendered rectangle's own aspect ratio exactly - true today
 * because the JPEG is never resized server-side, but not a contract this
 * module should bake in. Computing both factors independently means a future
 * mismatch bends the overlay instead of silently misplacing it in only one axis.
 */
export function scaleFactorsFor(
  rect: DisplayRect,
  frameW: number,
  frameH: number,
): { x: number; y: number } {
  return { x: rect.width / frameW, y: rect.height / frameH }
}
