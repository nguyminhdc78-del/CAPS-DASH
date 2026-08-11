import { lazy } from 'react'
import type { ReactNode } from 'react'
import { createBrowserRouter, RouterProvider } from 'react-router'

import { AppLayout } from './app-layout'
import { NotFoundPage } from './not-found-page'
import { RequireRoleRoute } from './require-role-route'
import { APP_ROUTES } from './route-definitions'

const LoginPage = lazy(() => import('@/features/auth/login-page'))
const KioskPage = lazy(() => import('@/features/kiosk/kiosk-page'))

const router = createBrowserRouter([
  { path: '/login', element: <LoginPage /> },
  {
    // Outside AppLayout on purpose: the kiosk is a lobby display, and a
    // sidebar, header and breadcrumb on a screen nobody can click are just
    // clutter. It still requires a session - resident tier, counts only.
    path: '/kiosk',
    element: (
      <RequireRoleRoute minRole="resident">
        <KioskPage />
      </RequireRoleRoute>
    ),
  },
  {
    element: <AppLayout />,
    children: [
      ...APP_ROUTES.map((route) => ({
        path: route.path,
        element: <RequireRoleRoute minRole={route.minRole}>{route.element}</RequireRoleRoute>,
      })),
      { path: '*', element: <NotFoundPage /> },
    ],
  },
])

export function AppRouter(): ReactNode {
  return <RouterProvider router={router} />
}
