import { Tag } from 'antd'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

import type { StreamStatus } from './camera-stream-manager'

const STATUS_COLOR: Record<StreamStatus, string> = {
  connecting: 'processing',
  authenticating: 'processing',
  streaming: 'success',
  reconnecting: 'warning',
  paused: 'default',
  closed: 'error',
}

const STATUS_KEY: Record<StreamStatus, string> = {
  connecting: 'statusConnecting',
  authenticating: 'statusAuthenticating',
  streaming: 'statusStreaming',
  reconnecting: 'statusReconnecting',
  paused: 'statusPaused',
  closed: 'statusClosed',
}

/** The connection state machine, rendered as a single localized badge. */
export function StreamStatusBadge({ status }: { status: StreamStatus }): ReactNode {
  const { t } = useTranslation('live')
  return <Tag color={STATUS_COLOR[status]}>{t(STATUS_KEY[status])}</Tag>
}
