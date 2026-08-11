import { useMemo } from 'react'

import { MAX_PAGE_SIZE } from '@/core/constants/ui-constants'
import { useCamerasQuery } from '@/features/cameras/use-cameras-queries'
import type { CameraRecord } from '@/features/cameras/use-cameras-queries'

/**
 * The live-view route is keyed by camera `code` (what the URL and the
 * cameras table both use), but the WS endpoint and the realtime protocol are
 * keyed by numeric `id`. There is no by-code lookup endpoint on the backend -
 * for a single-board site's small camera fleet, reusing the existing list
 * query is simpler than adding a REST endpoint for one call site.
 */
export function useCameraByCode(code: string | undefined): {
  camera: CameraRecord | null
  isLoading: boolean
} {
  const { data, isLoading } = useCamerasQuery({ limit: MAX_PAGE_SIZE })

  const camera = useMemo(() => {
    if (!code) return null
    return data?.items.find((item) => item.code === code) ?? null
  }, [data, code])

  return { camera, isLoading }
}
