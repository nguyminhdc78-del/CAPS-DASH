import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  DeleteOutlined,
  EditOutlined,
  QuestionCircleOutlined,
  SettingOutlined,
  VideoCameraOutlined,
} from '@ant-design/icons'
import { Button, Popconfirm, Space, Switch, Tag, Tooltip } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import dayjs from 'dayjs'
import relativeTime from 'dayjs/plugin/relativeTime'
import { Link } from 'react-router'

import { CameraConfidenceSlider } from './camera-confidence-slider'
import type { CameraRecord } from './use-cameras-queries'

dayjs.extend(relativeTime)

/** See `users-table-columns.tsx` for why this is two signatures, not one
 * with an optional second parameter. */
type Translate = {
  (key: string): string
  (key: string, options: Record<string, unknown>): string
}

export interface CamerasColumnActions {
  onEdit: (camera: CameraRecord) => void
  onToggleEnabled: (camera: CameraRecord) => void
  onDelete: (camera: CameraRecord) => void
  onOpenSettings: (camera: CameraRecord) => void
}

/** Column defs kept out of `cameras-table.tsx` so that file stays a thin wrapper. */
export function buildCamerasColumns(
  t: Translate,
  actions: CamerasColumnActions,
): ColumnsType<CameraRecord> {
  return [
    { title: t('camera:code'), dataIndex: 'code', fixed: 'left' },
    { title: t('camera:name'), dataIndex: 'name' },
    { title: t('camera:floor'), dataIndex: 'floor' },
    { title: t('camera:sourceType'), dataIndex: 'source_type' },
    {
      title: t('camera:enabled'),
      dataIndex: 'is_enabled',
      render: (isEnabled: boolean, record) => (
        <Switch
          checked={isEnabled}
          onChange={() => actions.onToggleEnabled(record)}
          aria-label={isEnabled ? t('camera:disabled') : t('camera:enabled')}
        />
      ),
    },
    {
      title: t('camera:online'),
      key: 'online',
      // `health` is null whenever no worker is running (disabled, or just
      // never polled yet) - that is "no data", not "offline", so it gets a
      // third, visibly distinct rendering rather than being folded into
      // either state.
      render: (_, record) => {
        if (record.health === null) {
          return <Tag icon={<QuestionCircleOutlined />}>{t('camera:noWorkerData')}</Tag>
        }
        return record.health.online ? (
          <Tag color="success" icon={<CheckCircleOutlined />}>
            {t('camera:online')}
          </Tag>
        ) : (
          <Tag color="error" icon={<CloseCircleOutlined />}>
            {t('camera:offline')}
          </Tag>
        )
      },
    },
    {
      title: t('camera:confidence'),
      key: 'confidence',
      render: (_, record) => <CameraConfidenceSlider cameraId={record.id} value={record.confidence} />,
    },
    {
      title: t('camera:processMs'),
      key: 'process_ms',
      render: (_, record) => (record.health ? record.health.process_ms.toFixed(0) : '—'),
    },
    {
      title: t('camera:errors'),
      key: 'errors',
      render: (_, record) => record.health?.errors ?? '—',
    },
    { title: t('camera:slotCount'), dataIndex: 'slot_count' },
    {
      title: t('camera:lastSeen'),
      dataIndex: 'last_seen_at',
      render: (value: string | null) =>
        value ? (
          <Tooltip title={dayjs(value).format('YYYY-MM-DD HH:mm')}>{dayjs(value).fromNow()}</Tooltip>
        ) : (
          t('camera:lastSeenNever')
        ),
    },
    {
      title: t('common:actions'),
      key: 'actions',
      fixed: 'right',
      render: (_, record) => (
        <Space>
          <Button size="small" icon={<EditOutlined />} onClick={() => actions.onEdit(record)}>
            {t('common:edit')}
          </Button>
          <Tooltip title={t('camera:sensorSettings')}>
            <Button
              size="small"
              icon={<SettingOutlined />}
              onClick={() => actions.onOpenSettings(record)}
              aria-label={t('camera:sensorSettings')}
            />
          </Tooltip>
          <Tooltip title={t('camera:roiEditor')}>
            <Link to={`/cameras/${record.id}/roi`}>
              <Button size="small" icon={<VideoCameraOutlined />} aria-label={t('camera:roiEditor')} />
            </Link>
          </Tooltip>
          <Tooltip title={t('camera:liveView')}>
            <Link to={`/cameras/${record.code}/live`}>
              <Button size="small" icon={<VideoCameraOutlined />} aria-label={t('camera:liveView')} />
            </Link>
          </Tooltip>
          <Popconfirm
            title={t('camera:deleteCameraConfirmTitle')}
            description={t('camera:deleteCameraConfirmContent', { count: record.slot_count })}
            onConfirm={() => actions.onDelete(record)}
            okText={t('common:confirm')}
            cancelText={t('common:cancel')}
            okButtonProps={{ danger: true }}
          >
            <Button size="small" danger icon={<DeleteOutlined />} aria-label={t('camera:deleteCamera')} />
          </Popconfirm>
        </Space>
      ),
    },
  ]
}
