import { WarningOutlined } from '@ant-design/icons'
import { Tag, Tooltip } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import dayjs from 'dayjs'
import type { Dayjs } from 'dayjs'

import { SuspectBadge } from '@/shared/components/suspect-badge'
import type { ParkingSessionRecord } from './use-sessions-queries'

/** See `users-table-columns.tsx` for why this is two signatures, not one
 * with an optional second parameter. */
type Translate = {
  (key: string): string
  (key: string, options: Record<string, unknown>): string
}

/** `3661` -> `"1h 01m"`. Shared with the summary line in `sessions-page.tsx`. */
export function formatDurationSeconds(seconds: number): string {
  const totalMinutes = Math.floor(seconds / 60)
  const hours = Math.floor(totalMinutes / 60)
  const minutes = totalMinutes % 60
  return hours > 0 ? `${hours}h ${String(minutes).padStart(2, '0')}m` : `${minutes}m`
}

/**
 * `now` drives the live duration for ongoing rows - passed down from
 * `sessions-table.tsx`'s ticking clock rather than read with `dayjs()`
 * here, so every row in one render shares exactly the same instant.
 */
export function buildSessionsColumns(t: Translate, now: Dayjs): ColumnsType<ParkingSessionRecord> {
  return [
    { title: t('history:floor'), dataIndex: 'floor' },
    { title: t('history:camera'), dataIndex: 'camera_code' },
    { title: t('history:slot'), dataIndex: 'slot_code' },
    {
      title: t('history:startedAt'),
      dataIndex: 'started_at',
      render: (value: string) => dayjs(value).format('YYYY-MM-DD HH:mm:ss'),
    },
    {
      title: t('history:endedAt'),
      key: 'ended_at',
      render: (_, record) =>
        record.ongoing ? (
          <Tag color="processing">{t('history:ongoing')}</Tag>
        ) : (
          dayjs(record.ended_at).format('YYYY-MM-DD HH:mm:ss')
        ),
    },
    {
      title: t('history:duration'),
      key: 'duration',
      render: (_, record) => {
        // A running session's server-reported duration is only accurate as
        // of the last fetch; while ongoing, recompute from `started_at`
        // against the shared `now` tick so the cell visibly counts up.
        const seconds = record.ongoing
          ? now.diff(dayjs(record.started_at), 'second')
          : (record.duration_seconds ?? 0)
        return formatDurationSeconds(Math.max(0, seconds))
      },
    },
    {
      title: t('history:flags'),
      key: 'flags',
      render: (_, record) => (
        <>
          {record.had_gap && (
            <Tooltip title={t('history:hadGapTooltip')}>
              <Tag color="orange" icon={<WarningOutlined />}>
                {t('history:hadGap')}
              </Tag>
            </Tooltip>
          )}
          {record.clock_suspect && <SuspectBadge />}
        </>
      ),
    },
  ]
}
