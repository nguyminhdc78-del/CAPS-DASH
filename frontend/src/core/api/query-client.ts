import { QueryClient } from '@tanstack/react-query'

import { ApiError } from './api-error'

export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        /**
         * Retrying a 4xx is pointless - the request was wrong, and repeating
         * it just multiplies the load on a small board. Retry server and
         * network failures only, and not many times.
         */
        retry: (failureCount, error) => {
          if (error instanceof ApiError && error.status < 500) return false
          return failureCount < 2
        },
        // Slot state changes on the order of seconds, not milliseconds.
        staleTime: 5_000,
        refetchOnWindowFocus: true,
      },
      mutations: {
        retry: false,
      },
    },
  })
}
