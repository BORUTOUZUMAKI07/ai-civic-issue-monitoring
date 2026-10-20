/**
 * The single source of truth for which routes require a signed-in session.
 *
 * Two independent layers need this list and they must not drift:
 *
 *  - `middleware.ts` (edge) redirects an unauthenticated *navigation* to
 *    `/login` so a protected page never even renders;
 *  - `lib/api.ts` (browser) only turns a 401 into a login redirect when the
 *    current page is protected. On a public page — the marketing landing
 *    fetches a couple of read-only endpoints before anyone signs in — a 401 is
 *    a normal answer, and bouncing the visitor to `/login` hid the page they
 *    opened and looked like a redirect loop.
 *
 * Keeping one list is what makes those two statements agree by construction.
 */
export const PROTECTED_PATHS = [
  "/dashboard",
  "/issues",
  "/map",
  "/engineers",
  "/settings",
  "/admin",
] as const;

/** True when `pathname` is one of the protected routes, or nested under one. */
export function isProtectedPath(pathname: string): boolean {
  return PROTECTED_PATHS.some(
    (p) => pathname === p || pathname.startsWith(p + "/"),
  );
}
