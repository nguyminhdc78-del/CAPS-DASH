/**
 * Every TanStack Query key used by the admin pages, in one place.
 *
 * A mutation that invalidates the wrong key silently stops refreshing a
 * list - scattering `['cameras', 'list']` literals across a dozen files is
 * how that typo goes unnoticed for weeks. Every query and every
 * invalidation imports from here instead, so a rename is one edit, not a
 * grep-and-pray across features.
 *
 * Slots/kiosk keys are included even though this phase does not build those
 * pages, so whoever builds them next does not have to edit this shared file.
 */

export interface CameraListParams {
  limit?: number
  offset?: number
}

export interface SlotListFilters {
  floor?: string
  state?: string
  cameraId?: number
}

/** Shared by `/history`, `/sessions` and the CSV export - all three accept
 * the same `from/to/slot_id/camera_code[/floor]` shape. Every field is
 * `| undefined` (not just optional) because `tsconfig`'s
 * `exactOptionalPropertyTypes` treats "declared and set to `undefined`" (a
 * cleared filter) as a different thing from "key omitted", and callers here
 * do the former. */
export interface HistoryRangeFilters {
  from?: string | undefined
  to?: string | undefined
  slotId?: number | undefined
  cameraCode?: string | undefined
  floor?: string | undefined
  limit?: number | undefined
  offset?: number | undefined
}

export interface HourlyStatsFilters {
  scopeType?: string | undefined
  scopeKey?: string | undefined
  from?: string | undefined
  to?: string | undefined
}

export interface AlertListFilters {
  acknowledged?: boolean | undefined
  type?: string | undefined
  severity?: string | undefined
  limit?: number | undefined
  offset?: number | undefined
}

export const queryKeys = {
  users: {
    all: () => ['users'] as const,
    list: () => ['users', 'list'] as const,
  },
  cameras: {
    all: () => ['cameras'] as const,
    list: (params: CameraListParams = {}) => ['cameras', 'list', params] as const,
    detail: (id: number) => ['cameras', 'detail', id] as const,
  },
  // Sensor settings (`GET/PATCH /cameras/{id}/settings`) are deliberately not
  // nested under `cameras.*`: they are a live device read, not a row from the
  // camera list, and mixing the two would make `cameras.all()` invalidation
  // either miss a stale sensor read or refetch it far more than it changes.
  cameraSettings: {
    detail: (cameraId: number | null) => ['cameraSettings', 'detail', cameraId] as const,
  },
  slots: {
    all: () => ['slots'] as const,
    // Filters are part of the key on purpose: two different floor/state
    // selections are two different cached results, not one that keeps
    // getting silently overwritten by whichever request lands last.
    list: (filters: SlotListFilters = {}) => ['slots', 'list', filters] as const,
  },
  summary: () => ['summary'] as const,
  history: {
    all: () => ['history'] as const,
    list: (filters: HistoryRangeFilters = {}) => ['history', 'list', filters] as const,
  },
  sessions: {
    all: () => ['sessions'] as const,
    list: (filters: HistoryRangeFilters = {}) => ['sessions', 'list', filters] as const,
  },
  stats: {
    all: () => ['stats'] as const,
    hourly: (filters: HourlyStatsFilters = {}) => ['stats', 'hourly', filters] as const,
  },
  alerts: {
    all: () => ['alerts'] as const,
    list: (filters: AlertListFilters = {}) => ['alerts', 'list', filters] as const,
  },
  // Keyed by the normalised query AND the vacated toggle: they are two
  // different questions ("where is it" vs "where was it last seen") with two
  // different answers, and sharing a key would serve one as the other.
  plates: {
    all: () => ['plates'] as const,
    search: (query: string, includeVacated: boolean) =>
      ['plates', 'search', query, includeVacated] as const,
  },
  // Deliberately NOT nested under `summary`/`plates` above: those serve the
  // authenticated staff endpoints (`/summary`, `/plates/search`). The public
  // kiosk hits separately-named `/public/*` endpoints with a narrower
  // response shape, and sharing a key would let a cached authenticated
  // response be served back as a public one, or vice versa.
  publicKiosk: {
    all: () => ['publicKiosk'] as const,
    summary: () => ['publicKiosk', 'summary'] as const,
    plateSearch: (query: string) => ['publicKiosk', 'plateSearch', query] as const,
  },
  system: {
    all: () => ['system'] as const,
    info: () => ['system', 'info'] as const,
  },
  // Lightweight camera/slot lookups that back filter dropdowns (history,
  // sessions, statistics). Deliberately its own key group rather than
  // reusing `cameras.list`/`slots.list`: those pages fetch a filtered,
  // default-page-size view, this fetches an unfiltered, max-page-size one -
  // sharing a key between two different requests is exactly the silent
  // cache collision this file exists to prevent.
  filterOptions: {
    cameras: () => ['filterOptions', 'cameras'] as const,
    slots: () => ['filterOptions', 'slots'] as const,
  },
} as const
