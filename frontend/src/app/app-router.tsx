import { lazy } from 'react'
import type { ReactNode } from 'react'
import { createBrowserRouter, RouterProvider } from 'react-router'

import { AppLayout } from './app-layout'
import { NotFoundPage } from './not-found-page'
import { RequireRoleRoute } from './require-role-route'
import { APP_ROUTES } from './route-definitions'

const LoginPage = lazy(() => import('@/features/auth/login-page'))

const router = createBrowserRouter([
  { path: '/login', element: <LoginPage /> },
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
