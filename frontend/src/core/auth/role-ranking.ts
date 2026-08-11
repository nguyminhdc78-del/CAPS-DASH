/**
 * Role ranks, mirroring the backend's `ROLE_RANK`.
 *
 * Compared by rank, never by equality: an admin must automatically be able to
 * do everything a guard can, without every route listing both roles. The one
 * place the two systems can drift is here, so it is one small file and nothing
 * else in the app hardcodes a role comparison.
 */

export const ROLES = ['resident', 'security', 'admin'] as const

export type Role = (typeof ROLES)[number]

const ROLE_RANK: Record<Role, number> = {
  resident: 1,
  security: 2,
  admin: 3,
}

export function rankOf(role: string | null | undefined): number {
  if (!role) return 0
  return ROLE_RANK[role as Role] ?? 0
}

/** True when `role` is at least as privileged as `minimum`. */
export function hasAtLeastRole(role: string | null | undefined, minimum: Role): boolean {
  return rankOf(role) >= ROLE_RANK[minimum]
}
