import { FullscreenExitOutlined, FullscreenOutlined, GlobalOutlined } from '@ant-design/icons'
import { Button, Empty, Flex, Typography } from 'antd'
import dayjs from 'dayjs'
import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

import { compareSlotCodes } from '@/features/slots/sort-slot-codes'
import { KioskFloorPanel } from './kiosk-floor-panel'
import { KioskOfflineBanner } from './kiosk-offline-banner'
import { useKioskSummary } from './use-kiosk-summary'

/** Ticks once a second, shared by the clock and the offline banner's "data
 * is N seconds old" text - one `setInterval` for both instead of two. */
function useNowTick(intervalMs: number): Date {
  const [now, setNow] = useState(() => new Date())
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), intervalMs)
    return () => clearInterval(id)
  }, [intervalMs])
  return now
}

function useIsFullscreen(): boolean {
  const [isFullscreen, setIsFullscreen] = useState(() => document.fullscreenElement !== null)
  useEffect(() => {
    const handler = (): void => setIsFullscreen(document.fullscreenElement !== null)
    document.addEventListener('fullscreenchange', handler)
    return () => document.removeEventListener('fullscreenchange', handler)
  }, [])
  return isFullscreen
}

/** Module scope: touches only `document`, nothing from component state, so
 * there is no reason to recreate it on every render. */
function toggleFullscreen(): void {
  // Graceful no-op when the Fullscreen API is unavailable (older embedded
  // browsers on the kiosk hardware itself) rather than throwing.
  if (!document.fullscreenEnabled) return
  if (document.fullscreenElement) {
    void document.exitFullscreen()
  } else {
    void document.documentElement.requestFullscreen()
  }
}

/**
 * Lobby display, route `/kiosk`, resident privilege.
 *
 * Renders COUNTS ONLY - no slot code, no camera name, no imagery of any
 * kind. That is not a UI choice made here; it is inherited directly from
 * `OccupancySummary` (`api/schemas/summary_schemas.py`), the one endpoint a
 * resident session can call: the schema itself carries no slot id, camera
 * id or polygon, so there is nothing more specific this page could show
 * even if it wanted to. A public lobby screen showing "space B-17 is empty"
 * instead of "42 free" would tell a passer-by exactly which car is away
 * from home - the privacy tier exists to prevent precisely that.
 *
 * `position: fixed; inset: 0` covers the app's sider/header regardless of
 * whether the router still wraps this route in `<AppLayout>` - route
 * wiring for `/kiosk` belongs to the orchestrator (see this phase's report),
 * not to this file, so the "no chrome" requirement is met defensively here
 * rather than assumed from the route tree.
 */
export default function KioskPage(): ReactNode {
  const { t, i18n } = useTranslation('kiosk')
  const { summary, isOffline, lastUpdatedAt } = useKioskSummary()
  const now = useNowTick(1_000)
  const isFullscreen = useIsFullscreen()

  const toggleLanguage = (): void => {
    void i18n.changeLanguage(i18n.language === 'vi' ? 'en' : 'vi')
  }

  const floors = [...(summary?.by_floor ?? [])].sort((a, b) => compareSlotCodes(a.floor, b.floor))

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        overflow: 'auto',
        padding: 24,
        background: 'var(--ant-color-bg-layout, #f5f5f5)',
        zIndex: 1000,
      }}
    >
      <Flex justify="space-between" align="center" style={{ marginBottom: 24 }}>
        <Typography.Title level={1} style={{ margin: 0 }}>
          {t('kiosk:title')}
        </Typography.Title>
        <Flex gap={16} align="center">
          <Typography.Title level={3} style={{ margin: 0, fontVariantNumeric: 'tabular-nums' }}>
            {dayjs(now).format('HH:mm:ss')}
          </Typography.Title>
          <Button icon={<GlobalOutlined />} onClick={toggleLanguage} aria-label={t('kiosk:languageToggleAriaLabel')}>
            {i18n.language.toUpperCase()}
          </Button>
          {document.fullscreenEnabled && (
            <Button
              icon={isFullscreen ? <FullscreenExitOutlined /> : <FullscreenOutlined />}
              onClick={toggleFullscreen}
              aria-label={isFullscreen ? t('kiosk:fullscreenExit') : t('kiosk:fullscreenEnter')}
            />
          )}
        </Flex>
      </Flex>

      {isOffline && <KioskOfflineBanner lastUpdatedAt={lastUpdatedAt} now={now} />}

      {floors.length === 0 ? (
        <Empty description={t('kiosk:noFloorData')} />
      ) : (
        <Flex gap={16} wrap style={{ marginTop: 16 }}>
          {floors.map((floor) => (
            <div key={floor.floor} style={{ flex: '1 1 320px' }}>
              <KioskFloorPanel floor={floor} />
            </div>
          ))}
        </Flex>
      )}
    </div>
  )
}
