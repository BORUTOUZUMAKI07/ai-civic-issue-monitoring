import type { NextConfig } from "next";

// Security headers applied to every response. The CSP is deliberately a
// mainstream baseline, not a strict nonce policy: Next.js ships inline
// bootstrap/RSC scripts, both of which need `'unsafe-inline'` in `script-src`.
// Tightening to nonces requires threading a per-request nonce through the RSC
// render, which is a separate change.
//
// `connect-src` allows `ws:`/`wss:` on purpose: the live issues feed opens a
// WebSocket to whatever backend `NEXT_PUBLIC_API_URL` points at, which is a
// different origin from the web app in development.
const isProd = process.env.NODE_ENV === "production";

const contentSecurityPolicy = [
  "default-src 'self'",
  "base-uri 'self'",
  "object-src 'none'",
  "frame-ancestors 'none'",
  "form-action 'self'",
  // Leaflet OpenStreetMap raster tiles.
  "img-src 'self' data: blob: https://*.tile.openstreetmap.org https://*.openstreetmap.org",
  "font-src 'self' data:",
  "style-src 'self' 'unsafe-inline'",
  "script-src 'self' 'unsafe-inline'",
  "connect-src 'self' ws: wss:",
  "worker-src 'self' blob:",
  "manifest-src 'self'",
  ...(isProd ? ["upgrade-insecure-requests"] : []),
].join("; ");

const securityHeaders = [
  { key: "Content-Security-Policy", value: contentSecurityPolicy },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "Permissions-Policy", value: "camera=(self), geolocation=(self), microphone=()" },
  // HSTS is only meaningful (and only "sticky") over HTTPS; sending it in
  // development would pin localhost to https and break the dev server.
  ...(isProd
    ? [{ key: "Strict-Transport-Security", value: "max-age=63072000; includeSubDomains; preload" }]
    : []),
];

const nextConfig: NextConfig = {
  output: "standalone",
  // React Compiler (stabilized at the top level in Next 16): Next applies it
  // via its SWC pipeline, so the only requirement beyond this flag is the
  // `babel-plugin-react-compiler` devDependency in package.json.
  reactCompiler: true,
  async headers() {
    return [
      {
        source: "/(.*)",
        headers: securityHeaders,
      },
    ];
  },
};

export default nextConfig;
