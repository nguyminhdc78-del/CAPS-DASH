import { Button } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import dayjs from 'dayjs'
import relativeTime from 'dayjs/plugin/relativeTime'

import { StateTag } from '@/shared/components/state-tag'
import type { SlotState } from '@/shared/components/state-tag'
import { compareSlotCodes } from './sort-slot-codes'
import type { SlotRecord } from './use-slots-queries'

dayjs.extend(relativeTime)

/** See `users-table-columns.tsx` for why this is two signatures, not one
 * with an optional second parameter. */
type Translate = {
  (key: string): string
  (key: string, options: Record<string, unknown>): string
}

export interface SlotsColumnActions {
  onViewDetail: (slot: SlotRecord) => void
  /** Resolves `camera_id` to a short display label; built once by the page
   * from the cameras list it already loaded for the camera filter. */
  cameraLabel: (cameraId: number) => string
}

const STATE_ORDER: Record<SlotState, number> = { FREE: 0, OCCUPIED: 1, UNKNOWN: 2 }

/** Column defs kept out of `slots-table.tsx` so that file stays a thin wrapper. */
export function buildSlotsColumns(t: Translate, actions: SlotsColumnActions): ColumnsType<SlotRecord> {
  return [
    {
      title: t('slot:code'),
      dataIndex: 'code',
      sorter: (a, b) => compareSlotCodes(a.code, b.code),
    },
    {
      title: t('slot:floor'),
      dataIndex: 'floor',
      sorter: (a, b) => compareSlotCodes(a.floor, b.floor),
    },
    {
      title: t('slot:camera'),
      key: 'camera',
      render: (_, record) => actions.cameraLabel(record.camera_id),
    },
    {
      title: t('slot:state'),
      dataIndex: 'current_state',
      sorter: (a, b) => STATE_ORDER[a.current_state] - STATE_ORDER[b.current_state],
      render: (state: SlotState) => <StateTag state={state} />,
    },
    {
      title: t('slot:since'),
      dataIndex: 'state_since',
      sorter: (a, b) => dayjs(a.state_since ?? 0).valueOf() - dayjs(b.state_since ?? 0).valueOf(),
      render: (value: string | null) => (value ? dayjs(value).fromNow() : '—'),
    },
    {
      title: t('common:actions'),
      key: 'actions',
      render: (_, record) => (
        <Button size="small" onClick={() => actions.onViewDetail(record)}>
          {t('slot:viewDetail')}
        </Button>
      ),
    },
  ]
}
