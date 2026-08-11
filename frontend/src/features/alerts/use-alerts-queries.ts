import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api } from '@/core/api/api-client'
import { queryKeys } from '@/core/api/query-keys'
import type { AlertListFilters } from '@/core/api/query-keys'
import { DEFAULT_PAGE_SIZE } from '@/core/constants/ui-constants'

/** Mirrors `AlertResponse` in backend/caps_dash/api/schemas/alert_schemas.py.
 * `message` is a developer fallback, never rendered directly when a
 * `message_code` translation exists - see `alerts-table-columns.tsx`. */
export interface AlertRecord {
  id: number
  alert_type: string
  severity: string
  entity_type: string
  entity_id: string
  message_code: string
  details_json: Record<string, unknown>
  message: string
  created_at: string
  acknowledged_at: string | null
  acknowledged_by_id: number | null
  clock_suspect: boolean
}

interface AlertsPage {
  items: AlertRecord[]
  total: number
  limit: number
  offset: number
}

function buildQuery(filters: AlertListFilters): string {
  const search = new URLSearchParams()
  if (filters.acknowledged !== undefined) search.set('acknowledged', String(filters.acknowledged))
  if (filters.type) search.set('type', filters.type)
  if (filters.severity) search.set('severity', filters.severity)
  search.set('limit', String(filters.limit ?? DEFAULT_PAGE_SIZE))
  search.set('offset', String(filters.offset ?? 0))
  return search.toString()
}

export function useAlertsQuery(filters: AlertListFilters) {
  return useQuery({
    queryKey: queryKeys.alerts.list(filters),
    queryFn: () => api.get<AlertsPage>(`/alerts?${buildQuery(filters)}`),
    placeholderData: (previous) => previous,
  })
}

export function useAcknowledgeAlertMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (alertId: number) => api.post<AlertRecord>(`/alerts/${alertId}/acknowledge`),
    onSuccess: () => {
      // Every filtered view of the list is affected by one row flipping
      // acknowledged - invalidate the whole `alerts` group, not just the
      // one filter combination currently on screen.
      void queryClient.invalidateQueries({ queryKey: queryKeys.alerts.all() })
    },
  })
}
