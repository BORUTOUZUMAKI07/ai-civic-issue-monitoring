# CivicPulse parity + deployment plan

Goal: close the remaining Nexus/url-shortner parity gaps, make the audit trail reporting-grade, add real deployment smoke automation, and remove temporary dependency-audit exceptions before merging to `github/main`.

## Current baseline (verified)

- Refresh families, 30s reuse grace, Redis rotation Lua, and family-scoped revocation already exist in `backend/src/domains/auth/services/auth_service.py`, but grace is hard-coded, `REFRESH_REVOKE_ON_REUSE` is missing, and no refresh/replay audit events are emitted.
- OAuth state/PKCE is stored server-side, but `consume_oauth_state()` uses non-atomic `get()` + `delete()` and the callback sets auth cookies directly on the frontend redirect. There is no one-time handoff code.
- Auth events are written to Redis and best-effort Mongo `audit_logs`, but there is no admin query/report/export surface and no redaction policy at the event layer.
- Deployed smoke checks are run manually with `.github/workflows/smoke.yml`; there is no legacy SSH deploy workflow.
- `pixi.lock` still has `dnspython 2.9.0` / `opentelemetry-api 1.45.1`; two CANNOT-fixed-yet allowlist entries remain in `backend/scripts/audit_deps.py`.

## Tasks

### 1. Refresh-token parity hardening
Acceptance:
- `REFRESH_REUSE_GRACE_SECONDS` and `REFRESH_REVOKE_ON_REUSE` are configurable with safe defaults.
- Replay inside grace rotates again; replay outside grace rejects and revokes only that family when enabled.
- Distinct `RefreshTokenReuse` error reaches the route and emits `refresh_reuse_detected`; successful refresh emits `refresh`.
- Tests cover grace boundary, family scoping, config flags, and Redis outage behaviour remains green.

### 2. Deeper audit/compliance reporting
Acceptance:
- Shared audit emitter redacts secrets/cookies/tokens from metadata, writes Redis hot list and durable Mongo document.
- Admin-only endpoints expose filtered event listing, a compliance report (summary, security events, GDPR lifecycle, controls, retention), and CSV export.
- `account_export` is audited; `audit_logs` joins the 90-day archival flow.
- Tests cover redaction, aggregation, filters, admin authorization, and fail-open writes.

### 3. One-time OAuth handoff code
Acceptance:
- State consumption uses one atomic Redis command; handoff code is random, TTL-bound, and consumed atomically with replay rejection.
- Callback redirects to `/login?code=<handoff>` with no token/state in the URL; redirect target is stored server-side.
- `POST /auth/oauth/exchange` validates the refresh token, rotates it, sets httpOnly cookies, and returns the user + safe redirect target.
- Frontend login page redeems `?code` once (StrictMode-safe), seeds `["me"]`, and redirects; 401 is shown as an error rather than triggering session-refresh bounce.
- Tests cover atomic single-use/concurrency, replay, callback contents, exchange success/failure, and BFF public-route access.

### 4. Deployment + dependency cleanup
Acceptance:
- Reusable deployed-smoke workflow and root script check frontend, BFF proxy, login/session/refresh, and optional admin surfaces against a real URL.
- `production-deploy.yml` points operators to the manual smoke run once collector/backend/frontend are READY.
- Docs list all required GitHub variables/secrets and how to run smoke manually.
- `dnspython>=2.9.2` and `opentelemetry-api>=1.45.2` floors are in `pixi.toml` + `backend/pyproject.toml`, lock is refreshed, and temporary allowlist entries are removed.

### 5. Verification + merge
Acceptance:
- Focused tests, full backend tests, frontend unit tests, lint, typecheck, bandit, dependency audit, and builds pass.
- Atomic commits on a feature branch; PR to `github/main`; CI green; merge with merge commit via remote `github`.
- Real deployment remains blocked until repository secrets/vars and a public URL are configured; report exact missing inputs.

## Order

1 → 2 → 3 → 4 → 5. Each task gets its own commit where practical.
