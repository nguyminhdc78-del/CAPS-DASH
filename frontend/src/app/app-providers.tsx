import { QueryClientProvider } from '@tanstack/react-query'
import { App as AntdApp } from 'antd'
import { useState } from 'react'
import type { ReactNode } from 'react'

import { createQueryClient } from '@/core/api/query-client'
import { AuthProvider } from '@/core/auth/auth-context'
import '@/core/i18n/i18n-config'
import { LocaleProvider } from '@/core/i18n/locale-provider'
import { ThemeProvider } from '@/core/theme/theme-provider'

/**
 * Provider order is load-bearing.
 *
 * Theme wraps Locale because LocaleProvider owns antd's ConfigProvider and
 * needs the theme tokens to hand it. Auth sits inside the query client so its
 * hooks can use queries, and inside AntdApp so it can raise messages.
 */
export function AppProviders({ children }: { children: ReactNode }): ReactNode {
  // Created once per app instance, not per render, and not at module scope -
  // module scope would share one cache across tests.
  const [queryClient] = useState(createQueryClient)

  return (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <LocaleProvider>
          <AntdApp>
            <AuthProvider>{children}</AuthProvider>
          </AntdApp>
        </LocaleProvider>
      </ThemeProvider>
    </QueryClientProvider>
  )
}
