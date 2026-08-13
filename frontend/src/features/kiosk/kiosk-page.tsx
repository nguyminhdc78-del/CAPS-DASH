import { FullscreenExitOutlined, FullscreenOutlined, GlobalOutlined } from '@ant-design/icons'
import { Button, ConfigProvider, Empty, Flex, Typography } from 'antd'
import dayjs from 'dayjs'
import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

import { compareSlotCodes } from '@/features/slots/sort-slot-codes'
import { KioskAvailabilityStrip } from './kiosk-availability-strip'
import { KioskDisabledNotice } from './kiosk-disabled-notice'
import { KioskFloorPanel } from './kiosk-floor-panel'
import { KIOSK_HUD_THEME } from './kiosk-hud-theme'
import { KioskOfflineBanner } from './kiosk-offline-banner'
import { KioskPlateSearch } from './kiosk-plate-search'
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
 * Public lobby display, route `/kiosk`. Unauthenticated - no session, no
 * login redirect, gated server-side by `PUBLIC_KIOSK_ENABLED` instead
 * (`app-router.tsx`, `use-kiosk-summary.ts`).
 *
 * The screen has one primary job for the person standing in front of it -
 * find their own car - so the plate search is the visual hero, dead centre.
 * Occupancy availability is the kiosk's second job (an arriving driver looking
 * for a free bay) and its *only* content when the plate-search kill-switch is
 * off, so it is demoted to a compact strip rather than deleted. See
 * `kiosk-availability-strip.tsx`.
 *
 * The look is a self-contained dark "HUD": the whole page forces its own dark
 * ConfigProvider (`KIOSK_HUD_THEME`) so a light admin session cannot turn the
 * lobby wall white, and it is responsive - a landscape lobby TV and a
 * customer's portrait phone share this one page (native focus raises the phone
 * keyboard; no on-screen keypad is built).
 *
 * Privacy note unchanged from before: FREE bay codes are shown deliberately
 * (a code here is a space, not a vehicle); plate search is where the real risk
 * lives and it ships with a per-IP rate limit, an audit row per search, and a
 * kill-switch that removes the box from the DOM entirely - see
 * `kiosk-plate-search.tsx`.
 */
export default function KioskPage(): ReactNode {
  const { t, i18n } = useTranslation('kiosk')
  const { summary, freeCodesByFloor, plateSearchEnabled, isOffline, isDisabled, lastUpdatedAt } =
    useKioskSummary()
  const now = useNowTick(1_000)
  const isFullscreen = useIsFullscreen()

  const toggleLanguage = (): void => {
    void i18n.changeLanguage(i18n.language === 'vi' ? 'en' : 'vi')
  }

  const floors = [...(summary?.by_floor ?? [])].sort((a, b) => compareSlotCodes(a.floor, b.floor))

  return (
    <ConfigProvider theme={KIOSK_HUD_THEME}>
      <div
        className="droom-kiosk"
        style={{
          position: 'fixed',
          inset: 0,
          overflow: 'auto',
          padding: 24,
          zIndex: 1000,
          display: 'flex',
          flexDirection: 'column',
        }}
      >
        <Flex justify="space-between" align="center" style={{ marginBottom: 16 }}>
          <Typography.Title level={3} className="droom-kiosk-title" style={{ margin: 0 }}>
            CAPS
          </Typography.Title>
          <Flex gap={12} align="center">
            <Typography.Text className="droom-clock">{dayjs(now).format('HH:mm:ss')}</Typography.Text>
            <Button
              icon={<GlobalOutlined />}
              onClick={toggleLanguage}
              aria-label={t('kiosk:languageToggleAriaLabel')}
            >
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

        {isDisabled ? <KioskDisabledNotice /> : null}

        {!isDisabled && isOffline && <KioskOfflineBanner lastUpdatedAt={lastUpdatedAt} now={now} />}

        {isDisabled ? null : plateSearchEnabled ? (
          // Find-your-car hero + demoted availability strip.
          <>
            <div className="kiosk-hero">
              <div className="kiosk-hero__eyebrow">{t('kiosk:title')}</div>
              <h1 className="kiosk-hero__title">{t('kiosk:searchTitle')}</h1>
              <KioskPlateSearch />
            </div>
            <div style={{ marginTop: 12 }}>
              <KioskAvailabilityStrip floors={floors} freeCodesByFloor={freeCodesByFloor} />
            </div>
          </>
        ) : floors.length === 0 ? (
          <Flex flex={1} align="center" justify="center">
            <Empty description={t('kiosk:noFloorData')} />
          </Flex>
        ) : (
          // Plate search killed: the availability board is the whole page, so
          // it keeps the big, read-from-across-the-lobby floor panels.
          <Flex gap={16} wrap flex={1} align="stretch" style={{ marginTop: 8 }}>
            {floors.map((floor) => (
              <div key={floor.floor} style={{ flex: '1 1 320px' }}>
                <KioskFloorPanel floor={floor} freeCodes={freeCodesByFloor[floor.floor] ?? []} />
              </div>
            ))}
          </Flex>
        )}
      </div>
    </ConfigProvider>
  )
}
