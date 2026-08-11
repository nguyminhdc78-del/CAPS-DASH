import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api } from '@/core/api/api-client'
import { queryKeys } from '@/core/api/query-keys'

/** Mirrors `TableRowCounts` in backend/caps_dash/api/schemas/system_schemas.py. */
export interface TableRowCounts {
  cameras: number
  parking_slots: number
  slot_state_history: number
  alerts: number
  audit_logs: number
  users: number
}

/** Mirrors `SystemInfoResponse`. */
export interface SystemInfo {
  disk_free_bytes: number
  disk_total_bytes: number
  table_row_counts: TableRowCounts
  schema_revision: string
  uptime_seconds: number
  clock_suspect: boolean
}

/** Mirrors `BackupResponse`. */
export interface BackupResult {
  backup_path: string
  size_bytes: number
  created_at: string
}

/** Mirrors `PurgeRequest`. `dry_run` defaults true server-side too, but is
 * always sent explicitly here - see `purge-panel.tsx` for why that default
 * must never be silently skipped on the client. */
export interface PurgeRequestInput {
  older_than_months?: number | undefined
  dry_run: boolean
}

/** Mirrors `PurgeResponse`. */
export interface PurgeResult {
  deleted_history_rows: number
  deleted_alert_rows: number
  dry_run: boolean
}

export function useSystemInfoQuery() {
  return useQuery({
    queryKey: queryKeys.system.info(),
    queryFn: () => api.get<SystemInfo>('/system/info'),
    // Uptime and disk figures drift slowly; a light poll keeps the page
    // honest without hammering an admin-only endpoint.
    refetchInterval: 30_000,
  })
}

export function useCreateBackupMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => api.post<BackupResult>('/system/backup'),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.system.info() })
    },
  })
}

export function usePurgeMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: PurgeRequestInput) => api.post<PurgeResult>('/system/purge', payload),
    onSuccess: (result) => {
      // A dry run changes nothing server-side; only a real purge needs the
      // row counts (and thus `/system/info`) refreshed.
      if (!result.dry_run) void queryClient.invalidateQueries({ queryKey: queryKeys.system.info() })
    },
  })
}
