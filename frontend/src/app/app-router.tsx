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
    // clutter. Unauthenticated ON PURPOSE - this is a public lobby screen,
    // not a resident view. Gating is done server-side by
    // PUBLIC_KIOSK_ENABLED (see use-kiosk-summary.ts / KioskDisabledNotice),
    // not by a session: no `RequireRoleRoute` here means no redirect to
    // /login and no flash of a login page for an anonymous visitor.
    path: '/kiosk',
    element: <KioskPage />,
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
