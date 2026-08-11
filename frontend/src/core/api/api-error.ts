/**
 * The typed form of the backend's error envelope.
 *
 * Every non-2xx response has the shape
 * `{ error: { code, message, request_id, details } }`. `code` is a stable
 * machine-readable string; the UI localises from that, never from `message`,
 * which is developer-facing English.
 */
export class ApiError extends Error {
  readonly code: string
  readonly requestId: string
  readonly details: Record<string, unknown>
  readonly status: number

  constructor(args: {
    code: string
    message: string
    requestId?: string
    details?: Record<string, unknown>
    status: number
  }) {
    super(args.message)
    this.name = 'ApiError'
    this.code = args.code
    this.requestId = args.requestId ?? ''
    this.details = args.details ?? {}
    this.status = args.status
  }
}

interface ErrorEnvelope {
  error?: {
    code?: string
    message?: string
    request_id?: string
    details?: Record<string, unknown>
  }
}

/**
 * Build an ApiError from a failed response.
 *
 * Falls back gracefully when the body is not our envelope at all - a proxy
 * returning HTML, or a network layer producing an empty body. Those cases must
 * still surface something a user can act on rather than a JSON parse crash.
 */
export async function apiErrorFromResponse(response: Response): Promise<ApiError> {
  let envelope: ErrorEnvelope = {}
  try {
    envelope = (await response.json()) as ErrorEnvelope
  } catch {
    // Body was not JSON. Nothing to recover; the status still tells us enough.
  }

  return new ApiError({
    code: envelope.error?.code ?? httpStatusToCode(response.status),
    message: envelope.error?.message ?? response.statusText,
    requestId: envelope.error?.request_id ?? '',
    details: envelope.error?.details ?? {},
    status: response.status,
  })
}

function httpStatusToCode(status: number): string {
  switch (status) {
    case 401:
      return 'AUTH_REQUIRED'
    case 403:
      return 'FORBIDDEN'
    case 404:
      return 'NOT_FOUND'
    case 409:
      return 'CONFLICT'
    case 422:
      return 'VALIDATION_FAILED'
    case 429:
      return 'RATE_LIMITED'
    default:
      return 'INTERNAL_ERROR'
  }
}
