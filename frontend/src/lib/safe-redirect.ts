/**
 * Validate a `?redirect=` value so post-login navigation cannot leave the site.
 *
 * The login page and the OAuth hand-off both forward this query parameter
 * straight into a navigation (`router.push` / `window.location.href`), where an
 * absolute or scheme-relative target (`https://evil.example`, `//evil.example`,
 * `/\evil.example`) sends the user off-site right after they authenticate — a
 * classic open redirect (CWE-601) that is trivial to weaponise for phishing.
 *
 * Only a same-site absolute path is accepted; anything else falls back to the
 * landing route. The backend applies the identical rule to the OAuth `redirect`
 * before embedding it in the signed state token
 * (`src/domains/auth/oauth.py::_decode_oauth_payload`), so this is defence in
 * depth for the two frontend paths that do not go through that check.
 */
export function safeInternalPath(
  value: string | null | undefined,
  fallback = "/dashboard",
): string {
  if (typeof value !== "string" || value.length === 0) return fallback;

  // A full URL (`https://…`, `javascript:…`) never starts with "/", so the
  // first-character check rejects it. A protocol-relative target (`//host`) or
  // a backslash-smuggled variant (`/\host`, which browsers normalise to
  // `//host`) is caught by the second character.
  if (value[0] !== "/") return fallback;
  if (value.length > 1 && (value[1] === "/" || value[1] === "\\")) return fallback;

  return value;
}
