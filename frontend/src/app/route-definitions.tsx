import {
  AlertOutlined,
  AppstoreOutlined,
  BarChartOutlined,
  CarOutlined,
  DashboardOutlined,
  HistoryOutlined,
  SettingOutlined,
  TeamOutlined,
  VideoCameraOutlined,
} from '@ant-design/icons'
import type { ReactNode } from 'react'

import type { Role } from '@/core/auth/role-ranking'
import { lazyWithReload } from './lazy-with-reload'

// `lazyWithReload`, not the bare `React.lazy`: a redeploy renames these
// hashed chunks, so a tab left open on the old index.html 404s the old
// filename. The wrapper turns that dead-end into a one-time self-heal reload.
const DashboardPage = lazyWithReload(() => import('@/features/dashboard/dashboard-page'))
const SlotsPage = lazyWithReload(() => import('@/features/slots/slots-page'))
const CamerasPage = lazyWithReload(() => import('@/features/cameras/cameras-page'))
const LiveViewPage = lazyWithReload(() => import('@/features/live/live-view-page'))
// Konva is a large dependency and only the ROI editor needs it. Lazy here is
// what keeps it out of the initial bundle everyone else downloads.
const RoiEditorPage = lazyWithReload(() => import('@/features/roi-editor/roi-editor-page'))
const PlateSearchPage = lazyWithReload(() => import('@/features/plates/plate-search-page'))
const HistoryPage = lazyWithReload(() => import('@/features/history/history-page'))
const StatisticsPage = lazyWithReload(() => import('@/features/statistics/statistics-page'))
const AlertsPage = lazyWithReload(() => import('@/features/alerts/alerts-page'))
const UsersPage = lazyWithReload(() => import('@/features/users/users-page'))
const SystemPage = lazyWithReload(() => import('@/features/system/system-page'))

export interface AppRoute {
  path: string
  element: ReactNode
  /** Minimum role. Compared by rank, so admin satisfies 'security'. */
  minRole: Role
  /** Menu label i18n key, `namespace:key`. Omit to keep it out of the menu. */
  labelKey?: string
  icon?: ReactNode
}

/**
 * One array drives both the router and the sidebar.
 *
 * Keeping them separate is how a build ends up with a menu entry leading to a
 * 403, or a route nobody can reach. Guarding and navigation read the same
 * `minRole` here.
 */
export const APP_ROUTES: AppRoute[] = [
  {
    path: '/',
    element: <DashboardPage />,
    minRole: 'resident',
    labelKey: 'system:dashboard',
    icon: <DashboardOutlined />,
  },
  {
    path: '/slots',
    element: <SlotsPage />,
    minRole: 'security',
    labelKey: 'slot:title',
    icon: <AppstoreOutlined />,
  },
  {
    // Camera admin (create/edit/delete/test-connection) is an admin-only
    // surface - the underlying source_url can carry device credentials, and
    // create/update/delete all require AdminOnly on the backend anyway.
    path: '/cameras',
    element: <CamerasPage />,
    minRole: 'admin',
    labelKey: 'camera:title',
    icon: <VideoCameraOutlined />,
  },
  {
    path: '/cameras/:code/live',
    element: <LiveViewPage />,
    minRole: 'security',
  },
  {
    // Admin only: drawing the slot map decides what every occupancy number in
    // the system means.
    path: '/cameras/:cameraId/roi',
    element: <RoiEditorPage />,
    minRole: 'admin',
  },
  {
    // Security and above only, matching the backend: a plate identifies a
    // vehicle and through it a person, and the PDR promises residents are
    // never shown which bay holds which car.
    path: '/plates',
    element: <PlateSearchPage />,
    minRole: 'security',
    labelKey: 'plate:title',
    icon: <CarOutlined />,
  },
  {
    path: '/history',
    element: <HistoryPage />,
    minRole: 'security',
    labelKey: 'system:history',
    icon: <HistoryOutlined />,
  },
  {
    path: '/statistics',
    element: <StatisticsPage />,
    minRole: 'security',
    labelKey: 'system:statistics',
    icon: <BarChartOutlined />,
  },
  {
    path: '/alerts',
    element: <AlertsPage />,
    minRole: 'security',
    labelKey: 'alert:title',
    icon: <AlertOutlined />,
  },
  {
    path: '/users',
    element: <UsersPage />,
    minRole: 'admin',
    labelKey: 'system:users',
    icon: <TeamOutlined />,
  },
  {
    path: '/system',
    element: <SystemPage />,
    minRole: 'admin',
    labelKey: 'system:title',
    icon: <SettingOutlined />,
  },
]
