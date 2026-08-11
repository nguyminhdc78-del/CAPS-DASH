import type { ColumnsType } from 'antd/es/table'
import dayjs from 'dayjs'

import { SuspectBadge } from '@/shared/components/suspect-badge'
import { AcknowledgeAlertButton } from './acknowledge-alert-button'
import { AlertSeverityTag } from './alert-severity-tag'
import type { AlertRecord } from './use-alerts-queries'

/** See `users-table-columns.tsx` for why this is two signatures, not one
 * with an optional second parameter. */
type Translate = {
  (key: string): string
  (key: string, options: Record<string, unknown>): string
}

/** Mirrors `AlertType` in backend/caps_dash/db/enums.py. */
const ALERT_TYPE_LABEL_KEY: Record<string, string> = {
  camera_offline: 'alert:cameraOffline',
  overstay: 'alert:overstay',
  disk_low: 'alert:diskLow',
  slot_overlap: 'alert:slotOverlap',
  clock_unsynced: 'alert:clockUnsynced',
}

/**
 * `message_code` + `details_json` -> a localized sentence.
 *
 * `message_code` looks like `"alert.overstay"`; the `alert:messages.*` tree
 * holds the templates (`{{slot_code}}`, `{{hours}}`, ...) keyed by the part
 * after the dot, with `details_json`'s own snake_case keys interpolated
 * directly - no renaming needed since the backend and the templates already
 * agree on names. `alert.message` is the fallback for any code without a
 * template yet (see `alert_schemas.py`'s docstring: it must never be shown
 * when a real translation exists, but showing it when one does not is the
 * whole point of having a fallback).
 */
export function localizeAlertMessage(t: Translate, alert: AlertRecord): string {
  const suffix = alert.message_code.startsWith('alert.')
    ? alert.message_code.slice('alert.'.length)
    : alert.message_code
  const translated = t(`alert:messages.${suffix}`, { ...alert.details_json, defaultValue: '' })
  return translated || alert.message
}

export interface AlertsColumnActions {
  onAcknowledgeError: (message: string) => void
}

export function buildAlertsColumns(t: Translate, actions: AlertsColumnActions): ColumnsType<AlertRecord> {
  return [
    {
      title: t('alert:createdAt'),
      dataIndex: 'created_at',
      render: (value: string) => dayjs(value).format('YYYY-MM-DD HH:mm:ss'),
    },
    {
      title: t('alert:type'),
      dataIndex: 'alert_type',
      render: (value: string) => t(ALERT_TYPE_LABEL_KEY[value] ?? 'alert:type'),
    },
    {
      title: t('alert:severity'),
      dataIndex: 'severity',
      render: (value: string) => <AlertSeverityTag severity={value} />,
    },
    {
      title: t('alert:message'),
      key: 'message',
      render: (_, record) => localizeAlertMessage(t, record),
    },
    {
      title: t('alert:reliability'),
      key: 'clock_suspect',
      render: (_, record) => (record.clock_suspect ? <SuspectBadge /> : null),
    },
    {
      title: t('common:actions'),
      key: 'actions',
      render: (_, record) => (
        <AcknowledgeAlertButton alert={record} onError={actions.onAcknowledgeError} />
      ),
    },
  ]
}
