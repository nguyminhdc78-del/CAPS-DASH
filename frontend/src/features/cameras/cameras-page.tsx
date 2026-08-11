import { PlusOutlined } from '@ant-design/icons'
import { App, Button, Card } from 'antd'
import { useState } from 'react'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

import { useErrorMessage } from '@/core/i18n/use-error-message'
import { CameraFormDrawer } from './camera-form-drawer'
import { CamerasTable } from './cameras-table'
import { useCamerasQuery, useDeleteCameraMutation, useUpdateCameraMutation } from './use-cameras-queries'
import type { CameraRecord } from './use-cameras-queries'

export default function CamerasPage(): ReactNode {
  const { t } = useTranslation(['camera', 'common'])
  const { message } = App.useApp()
  const toMessage = useErrorMessage()

  const { data, isLoading } = useCamerasQuery()
  const updateCamera = useUpdateCameraMutation()
  const deleteCamera = useDeleteCameraMutation()

  const [editingCamera, setEditingCamera] = useState<CameraRecord | null>(null)
  const [drawerOpen, setDrawerOpen] = useState(false)

  const handleAdd = (): void => {
    setEditingCamera(null)
    setDrawerOpen(true)
  }

  const handleEdit = (camera: CameraRecord): void => {
    setEditingCamera(camera)
    setDrawerOpen(true)
  }

  const handleToggleEnabled = async (camera: CameraRecord): Promise<void> => {
    try {
      await updateCamera.mutateAsync({ id: camera.id, is_enabled: !camera.is_enabled })
    } catch (caught) {
      void message.error(toMessage(caught))
    }
  }

  const handleDelete = async (camera: CameraRecord): Promise<void> => {
    try {
      await deleteCamera.mutateAsync(camera.id)
      void message.success(t('common:deleted'))
    } catch (caught) {
      void message.error(toMessage(caught))
    }
  }

  return (
    <Card
      title={t('camera:title')}
      extra={
        <Button type="primary" icon={<PlusOutlined />} onClick={handleAdd}>
          {t('camera:addCamera')}
        </Button>
      }
    >
      <CamerasTable
        data={data?.items ?? []}
        loading={isLoading}
        onEdit={handleEdit}
        onToggleEnabled={(camera) => void handleToggleEnabled(camera)}
        onDelete={(camera) => void handleDelete(camera)}
      />

      <CameraFormDrawer open={drawerOpen} camera={editingCamera} onClose={() => setDrawerOpen(false)} />
    </Card>
  )
}
