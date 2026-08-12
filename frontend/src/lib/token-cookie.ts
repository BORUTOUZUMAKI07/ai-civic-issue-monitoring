const COOKIE_NAME = "access_token"
const REFRESH_COOKIE_NAME = "refresh_token"

function isSecureContext(): boolean {
  if (typeof window === "undefined") return false
  return window.location.protocol === "https:"
}

export function setTokenCookie(token: string) {
  if (typeof document === "undefined") return
  const secure = isSecureContext() ? "; Secure" : ""
  document.cookie = `${COOKIE_NAME}=${token}; path=/; max-age=604800; SameSite=Lax${secure}`
}

export function setRefreshTokenCookie(token: string) {
  if (typeof document === "undefined") return
  const secure = isSecureContext() ? "; Secure" : ""
  document.cookie = `${REFRESH_COOKIE_NAME}=${token}; path=/; max-age=2592000; SameSite=Lax${secure}`
}

export function clearTokenCookies() {
  if (typeof document === "undefined") return
  document.cookie = `${COOKIE_NAME}=; path=/; max-age=0`
  document.cookie = `${REFRESH_COOKIE_NAME}=; path=/; max-age=0`
}
