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
import { lazy } from 'react'
import type { ReactNode } from 'react'

import type { Role } from '@/core/auth/role-ranking'

const DashboardPage = lazy(() => import('@/features/dashboard/dashboard-page'))
const SlotsPage = lazy(() => import('@/features/slots/slots-page'))
const CamerasPage = lazy(() => import('@/features/cameras/cameras-page'))
const LiveViewPage = lazy(() => import('@/features/live/live-view-page'))
// Konva is a large dependency and only the ROI editor needs it. Lazy here is
// what keeps it out of the initial bundle everyone else downloads.
const RoiEditorPage = lazy(() => import('@/features/roi-editor/roi-editor-page'))
const PlateSearchPage = lazy(() => import('@/features/plates/plate-search-page'))
const HistoryPage = lazy(() => import('@/features/history/history-page'))
const StatisticsPage = lazy(() => import('@/features/statistics/statistics-page'))
const AlertsPage = lazy(() => import('@/features/alerts/alerts-page'))
const UsersPage = lazy(() => import('@/features/users/users-page'))
const SystemPage = lazy(() => import('@/features/system/system-page'))

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
