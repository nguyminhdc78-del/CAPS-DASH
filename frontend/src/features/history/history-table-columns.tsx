import { Space } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import dayjs from 'dayjs'

import { StateTag } from '@/shared/components/state-tag'
import type { SlotState } from '@/shared/components/state-tag'
import { SuspectBadge } from '@/shared/components/suspect-badge'
import type { SlotStateChangeRecord } from './use-history-queries'

/** See `users-table-columns.tsx` for why this is two signatures, not one
 * with an optional second parameter. */
type Translate = {
  (key: string): string
  (key: string, options: Record<string, unknown>): string
}

/** Column defs kept out of `history-table.tsx` so that file stays a thin wrapper. */
export function buildHistoryColumns(t: Translate): ColumnsType<SlotStateChangeRecord> {
  return [
    {
      title: t('history:changedAt'),
      dataIndex: 'changed_at',
      render: (value: string) => dayjs(value).format('YYYY-MM-DD HH:mm:ss'),
    },
    { title: t('history:camera'), dataIndex: 'camera_code' },
    { title: t('history:slot'), dataIndex: 'slot_code' },
    { title: t('history:floor'), dataIndex: 'floor' },
    {
      title: t('history:transition'),
      key: 'transition',
      render: (_, record) => (
        <Space size="small">
          <StateTag state={record.previous_state as SlotState} />
          {'→'}
          <StateTag state={record.new_state as SlotState} />
        </Space>
      ),
    },
    {
      title: t('history:reliability'),
      key: 'clock_suspect',
      render: (_, record) => (record.clock_suspect ? <SuspectBadge /> : null),
    },
  ]
}
