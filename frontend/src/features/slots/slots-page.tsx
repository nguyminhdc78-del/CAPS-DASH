import { AppstoreOutlined, TableOutlined } from '@ant-design/icons'
import { Alert, Card, Flex, Segmented, Select, Space } from 'antd'
import { useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

import { MAX_PAGE_SIZE } from '@/core/constants/ui-constants'
import { useErrorMessage } from '@/core/i18n/use-error-message'
import { useCamerasQuery } from '@/features/cameras/use-cameras-queries'
import { SlotStateLegend } from '@/shared/components/slot-state-legend'
import type { SlotState } from '@/shared/components/state-tag'
import { SlotCountStrip } from './slot-count-strip'
import { SlotDetailDrawer } from './slot-detail-drawer'
import { SlotGrid } from './slot-grid'
import { compareSlotCodes, sortSlots } from './sort-slot-codes'
import { SlotsTable } from './slots-table'
import { useSlotsQuery, useSummaryQuery } from './use-slots-queries'
import type { SlotRecord } from './use-slots-queries'

const ALL_STATES: SlotState[] = ['FREE', 'OCCUPIED', 'UNKNOWN']
const STATE_LABEL_KEY: Record<SlotState, string> = {
  FREE: 'slot:stateFree',
  OCCUPIED: 'slot:stateOccupied',
  UNKNOWN: 'slot:stateUnknown',
}

/**
 * Security's parking overview: floor + state + camera filters, a grid/table
 * toggle, and a click-through detail drawer.
 *
 * Only `floor` ever changes the network request (`useSlotsQuery`'s query
 * key). `state` and `camera` filter that same fetched array client-side -
 * see `use-slots-queries.ts`'s docstring for why: it keeps the count strip
 * and the visible list reading from one shared source of truth instead of
 * two queries that could momentarily disagree.
 */
export default function SlotsPage(): ReactNode {
  const { t } = useTranslation(['slot', 'common'])
  const toMessage = useErrorMessage()

  const [floor, setFloor] = useState<string | null>(null)
  const [stateFilter, setStateFilter] = useState<SlotState | null>(null)
  const [cameraFilter, setCameraFilter] = useState<number | null>(null)
  const [view, setView] = useState<'grid' | 'table'>('grid')
  const [selectedSlot, setSelectedSlot] = useState<SlotRecord | null>(null)

  const summaryQuery = useSummaryQuery()
  // `exactOptionalPropertyTypes` rejects `{ floor: undefined }` - the key
  // must be absent, not present-with-undefined - so this branches instead
  // of spreading a maybe-undefined value into the filters object.
  const slotsQuery = useSlotsQuery(floor === null ? {} : { floor })
  const camerasQuery = useCamerasQuery({ limit: MAX_PAGE_SIZE })

  const floorOptions = useMemo(
    () => (summaryQuery.data?.by_floor.map((entry) => entry.floor) ?? []).sort(compareSlotCodes),
    [summaryQuery.data],
  )
  const cameraById = useMemo(
    () => new Map((camerasQuery.data?.items ?? []).map((camera) => [camera.id, camera])),
    [camerasQuery.data],
  )
  const cameraOptions = useMemo(
    () =>
      [...cameraById.values()]
        .sort((a, b) => compareSlotCodes(a.code, b.code))
        .map((camera) => ({ value: camera.id, label: `${camera.code} — ${camera.name}` })),
    [cameraById],
  )
  const cameraLabel = (cameraId: number): string => {
    const camera = cameraById.get(cameraId)
    return camera ? `${camera.code} — ${camera.name}` : t('slot:noCamera')
  }
  const cameraLinkTo = (cameraId: number): string | null => {
    const camera = cameraById.get(cameraId)
    return camera ? `/cameras/${camera.code}/live` : null
  }

  const allSlotsForFloor = useMemo(() => sortSlots(slotsQuery.data?.items ?? []), [slotsQuery.data])
  const visibleSlots = useMemo(
    () =>
      allSlotsForFloor.filter(
        (slot) =>
          (stateFilter === null || slot.current_state === stateFilter) &&
          (cameraFilter === null || slot.camera_id === cameraFilter),
      ),
    [allSlotsForFloor, stateFilter, cameraFilter],
  )

  return (
    <Card title={t('slot:title')}>
      <Space direction="vertical" size={16} style={{ width: '100%' }}>
        {slotsQuery.isError && <Alert type="error" showIcon message={toMessage(slotsQuery.error)} />}

        <Flex gap={12} wrap align="center">
          <Select
            allowClear
            placeholder={t('slot:allFloors')}
            aria-label={t('slot:floor')}
            style={{ minWidth: 140 }}
            value={floor}
            onChange={(value: string | null) => setFloor(value ?? null)}
            options={floorOptions.map((value) => ({ value, label: value }))}
          />
          <Select
            allowClear
            placeholder={t('slot:allStates')}
            aria-label={t('slot:state')}
            style={{ minWidth: 160 }}
            value={stateFilter}
            onChange={(value: SlotState | null) => setStateFilter(value ?? null)}
            options={ALL_STATES.map((state) => ({ value: state, label: t(STATE_LABEL_KEY[state]) }))}
          />
          <Select
            allowClear
            showSearch
            placeholder={t('slot:allCameras')}
            aria-label={t('slot:camera')}
            style={{ minWidth: 220 }}
            value={cameraFilter}
            onChange={(value: number | null) => setCameraFilter(value ?? null)}
            options={cameraOptions}
            filterOption={(input, option) =>
              (option?.label ?? '').toLowerCase().includes(input.toLowerCase())
            }
          />
          <Segmented
            aria-label={t('slot:viewToggleLabel')}
            value={view}
            onChange={(value) => setView(value as 'grid' | 'table')}
            options={[
              { value: 'grid', icon: <AppstoreOutlined />, label: t('slot:viewGrid') },
              { value: 'table', icon: <TableOutlined />, label: t('slot:viewTable') },
            ]}
          />
        </Flex>

        <SlotStateLegend />

        <SlotCountStrip rows={allSlotsForFloor} summary={summaryQuery.data} floor={floor} />

        {view === 'grid' ? (
          <SlotGrid slots={visibleSlots} onSelect={setSelectedSlot} />
        ) : (
          <SlotsTable
            data={visibleSlots}
            loading={slotsQuery.isLoading}
            onViewDetail={setSelectedSlot}
            cameraLabel={cameraLabel}
          />
        )}
      </Space>

      <SlotDetailDrawer
        slot={selectedSlot}
        cameraLabel={selectedSlot ? cameraLabel(selectedSlot.camera_id) : ''}
        cameraLinkTo={selectedSlot ? cameraLinkTo(selectedSlot.camera_id) : null}
        onClose={() => setSelectedSlot(null)}
      />
    </Card>
  )
}
