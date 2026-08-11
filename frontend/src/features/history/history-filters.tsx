import { Button, DatePicker, Select, Space } from 'antd'
import dayjs from 'dayjs'
import type { Dayjs } from 'dayjs'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

import { useCameraOptionsQuery, useFloorOptions, useSlotOptionsQuery } from '@/shared/hooks/use-parking-filter-options'
import { HISTORY_MAX_SPAN_DAYS } from './use-history-queries'

const { RangePicker } = DatePicker

/** Module scope on purpose - captures nothing from the component, so there
 * is no reason to recreate it on every render. */
function disabledDate(current: Dayjs, info: { from?: Dayjs }): boolean {
  if (current.isAfter(dayjs().endOf('day'))) return true
  if (info.from) return Math.abs(current.diff(info.from, 'day')) > HISTORY_MAX_SPAN_DAYS
  return false
}

export interface HistoryFilterValues {
  range: [Dayjs, Dayjs]
  slotId: number | undefined
  cameraCode: string | undefined
  floor: string | undefined
}

interface HistoryFiltersProps {
  value: HistoryFilterValues
  onChange: (value: HistoryFilterValues) => void
}

/**
 * Date range is mandatory (no "clear" affordance) and soft-capped at
 * `HISTORY_MAX_SPAN_DAYS` via `disabledDate` - the server enforces the real
 * cap and returns `RANGE_TOO_WIDE` regardless (see `history-page.tsx`), this
 * just stops most operators from building an invalid range in the first
 * place. Floor/camera/slot filters mirror the query params `/history` and
 * `/sessions` both accept.
 */
export function HistoryFilters({ value, onChange }: HistoryFiltersProps): ReactNode {
  const { t } = useTranslation('history')
  const { data: cameras } = useCameraOptionsQuery()
  const { data: slots } = useSlotOptionsQuery()
  const floors = useFloorOptions()

  const filteredSlots = (slots?.items ?? []).filter(
    (slot) => !value.floor || slot.floor === value.floor,
  )

  return (
    <Space wrap style={{ marginBottom: 16 }}>
      <RangePicker
        value={value.range}
        allowClear={false}
        disabledDate={disabledDate}
        onChange={(range) => {
          if (!range?.[0] || !range[1]) return
          onChange({ ...value, range: [range[0], range[1]] })
        }}
      />
      <Select
        allowClear
        placeholder={t('filterFloor')}
        style={{ width: 140 }}
        value={value.floor}
        onChange={(floor: string | undefined) => onChange({ ...value, floor, slotId: undefined })}
        options={floors.map((floor) => ({ value: floor, label: floor }))}
      />
      <Select
        allowClear
        placeholder={t('filterCamera')}
        style={{ width: 180 }}
        value={value.cameraCode}
        onChange={(cameraCode: string | undefined) => onChange({ ...value, cameraCode })}
        options={(cameras?.items ?? []).map((camera) => ({ value: camera.code, label: camera.code }))}
      />
      <Select
        allowClear
        placeholder={t('filterSlot')}
        style={{ width: 160 }}
        value={value.slotId}
        onChange={(slotId: number | undefined) => onChange({ ...value, slotId })}
        options={filteredSlots.map((slot) => ({ value: slot.id, label: `${slot.code} (${slot.floor})` }))}
      />
      <Button
        onClick={() =>
          onChange({
            range: value.range,
            slotId: undefined,
            cameraCode: undefined,
            floor: undefined,
          })
        }
      >
        {t('clearFilters')}
      </Button>
    </Space>
  )
}
