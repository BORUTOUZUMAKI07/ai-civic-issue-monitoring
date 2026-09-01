'use strict'

// CivicPulse New Relic Node.js agent configuration (Hybrid Agent for Next.js).
//
// The `newrelic` package plus this config are only activated when a real
// license key is present. src/instrumentation.ts checks NEW_RELIC_LICENSE_KEY
// before loading the agent, so in development/CI (where the key is absent)
// the app runs with zero New Relic footprint and the build is unaffected.
//
// Native Next.js OpenTelemetry spans drive APM via the Hybrid Agent; we
// disable the agent's own http/next/undici instrumentation to avoid
// duplicate client spans (see https://docs.newrelic.com for details).

module.exports = {
  app_name: [process.env.NEW_RELIC_APP_NAME || 'CivicPulse-Web'],
  license_key: process.env.NEW_RELIC_LICENSE_KEY,
  opentelemetry: {
    enabled: true,
  },
  instrumentation: {
    http: { enabled: false },
    next: { enabled: false },
    undici: { enabled: false },
  },
  allow_all_headers: true,
  attributes: {
    enabled: true,
  },
  logging: {
    level: 'info',
  },
}
