import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api } from '@/core/api/api-client'
import { queryKeys } from '@/core/api/query-keys'
import type { Role } from '@/core/auth/role-ranking'

/** Mirrors `UserResponse` in backend/caps_dash/api/schemas/user_schemas.py. */
export interface UserAccount {
  id: number
  username: string
  display_name: string
  role: Role
  is_active: boolean
  last_login_at: string | null
  created_at: string
}

export interface CreateUserInput {
  username: string
  password: string
  display_name: string
  role: Role
}

/** Mirrors `UpdateUserRequest`: every field optional, a partial update. */
export interface UpdateUserInput {
  display_name?: string
  role?: Role
  is_active?: boolean
}

export function useUsersQuery() {
  return useQuery({
    queryKey: queryKeys.users.list(),
    queryFn: () => api.get<UserAccount[]>('/users'),
  })
}

export function useCreateUserMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (input: CreateUserInput) => api.post<UserAccount>('/users', input),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.users.list() })
    },
  })
}

export function useUpdateUserMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, ...input }: UpdateUserInput & { id: number }) =>
      api.patch<UserAccount>(`/users/${id}`, input),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.users.list() })
    },
  })
}

/**
 * The backend has no `DELETE /users/{id}` - the last-admin protection lives
 * in `update_user`, guarding role changes and deactivation alike, and there
 * is deliberately no way to erase an account's audit trail. Deactivating
 * (via `useUpdateUserMutation`) is the real "remove access" action; this
 * mutation only resets a password.
 */
export function useResetPasswordMutation() {
  return useMutation({
    mutationFn: ({ id, newPassword }: { id: number; newPassword: string }) =>
      api.post(`/users/${id}/reset-password`, { new_password: newPassword }),
  })
}
