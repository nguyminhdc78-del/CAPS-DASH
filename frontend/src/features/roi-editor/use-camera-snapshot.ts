import { useCallback, useEffect, useState } from 'react'

import { apiErrorFromResponse } from '@/core/api/api-error'
import { authTokenStore } from '@/core/api/auth-token-store'
import { refreshAccessToken } from '@/core/api/refresh-single-flight'

/**
 * Loads `GET /cameras/{id}/snapshot` as an `HTMLImageElement`.
 *
 * Not `api.get<T>()`: that helper always parses the body as JSON, but this
 * endpoint returns raw JPEG bytes with `Cache-Control: no-store` (see
 * camera_diagnostics_routes.py). Auth/refresh-retry is reproduced here at the
 * fetch layer instead - the shared client has no "give me the raw Response"
 * escape hatch, and adding one is out of this phase's file ownership.
 *
 * The object URL is revoked on unmount/refetch - the snapshot must not
 * outlive the component on a shared security-room machine.
 */

export interface SnapshotState {
  status: 'idle' | 'loading' | 'ready' | 'error'
  image: HTMLImageElement | null
  error: unknown
}

async function fetchSnapshotBlob(cameraId: number, retryOnUnauthorized = true): Promise<Blob> {
  const headers = new Headers()
  const token = authTokenStore.get()
  if (token) headers.set('Authorization', `Bearer ${token}`)

  const response = await fetch(`/api/cameras/${cameraId}/snapshot`, {
    headers,
    credentials: 'same-origin',
  })

  if (response.status === 401 && retryOnUnauthorized) {
    if (await refreshAccessToken()) return fetchSnapshotBlob(cameraId, false)
    throw await apiErrorFromResponse(response)
  }
  if (!response.ok) throw await apiErrorFromResponse(response)
  return response.blob()
}

function decodeImage(blob: Blob): Promise<{ image: HTMLImageElement; objectUrl: string }> {
  const objectUrl = URL.createObjectURL(blob)
  return new Promise((resolve, reject) => {
    const image = new Image()
    image.onload = () => resolve({ image, objectUrl })
    image.onerror = () => {
      URL.revokeObjectURL(objectUrl)
      reject(new Error('Snapshot image failed to decode'))
    }
    image.src = objectUrl
  })
}

export function useCameraSnapshot(cameraId: number): SnapshotState & { retry: () => void } {
  const [state, setState] = useState<SnapshotState>({ status: 'idle', image: null, error: null })
  const [reloadToken, setReloadToken] = useState(0)

  useEffect(() => {
    let cancelled = false
    let objectUrl: string | null = null
    setState({ status: 'loading', image: null, error: null })

    fetchSnapshotBlob(cameraId)
      .then(decodeImage)
      .then(({ image, objectUrl: url }) => {
        if (cancelled) {
          URL.revokeObjectURL(url)
          return
        }
        objectUrl = url
        setState({ status: 'ready', image, error: null })
      })
      .catch((error: unknown) => {
        if (!cancelled) setState({ status: 'error', image: null, error })
      })

    return () => {
      cancelled = true
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [cameraId, reloadToken])

  const retry = useCallback(() => setReloadToken((n) => n + 1), [])
  return { ...state, retry }
}
