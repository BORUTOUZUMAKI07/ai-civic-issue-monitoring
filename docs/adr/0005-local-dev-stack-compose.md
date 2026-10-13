# ADR-0005: Local dev datastores behind a compose `dev` profile

- **Status**: Accepted
- **Date**: 2026-10-11

## Context

`docker compose up` existed but could not actually boot the application: the
backend service's environment used `:?`-required interpolation
(`DATABASE_URL:?DATABASE_URL must be set`, `REDIS_URL:?`, `MONGODB_URI:?`,
`OPENAI_API_KEY:?`, `HF_TOKEN:?`, `SECRET_KEY:?`), so staring the stack without
a hand-built `.env` failed at interpolation time — before a single container
ran. Despite that, `REDIS_URL` was also pure dead weight: `src/core/redis.py`
only ever constructed an Upstash REST adapter, so no Redis the compose file
provided could ever be used by the app.

The goal ("reproducible environment") is: a developer clones the repo, runs one
compose command, and gets a working app. Production deployments (Render/Aiven,
env-var-driven) must keep the option of external Postgres/Redis/Mongo and must
not pick up local-only defaults as a footgun. The `dev` compose profile —
active only with `--profile dev` — is the mechanism Compose provides for
exactly this.

## Decision

1. **Add `postgres` (16-alpine), `redis` (7-alpine) and `mongo` (7) services**
   to `docker/docker-compose.yml`, each under `profiles: ["dev"]` with a
   healthcheck and a named volume, on the existing `frontend-net`. Plain
   `docker compose up` therefore does not start them (production stack shape
   unchanged); `docker compose --profile dev up` boots the full local stack.
2. **Backend env vars get local-first defaults** for the datastores, using
   `:-` interpolation: `DATABASE_URL` → `postgresql://civicpulse:changeme@postgres:5432/civicpulse`,
   `REDIS_URL` → `redis://redis:6379`, `MONGODB_URI` → `mongodb://mongo:27017`,
   `UPSTASH_REDIS_REST_URL`/`TOKEN` → empty. Explicitly set vars always win,
   so Aiven/Upstash/Atlas deployments are unaffected.
3. **Drop the `ASYNC_DATABASE_URI` line from compose.** The config
   (`src/core/config.py`) already builds the asyncpg URI from `DATABASE_URL`
   via `build_async_uri`; previously compose force-fed the *raw* `DATABASE_URL`
   into `ASYNC_DATABASE_URI`, so a `postgresql://` URL crashed
   `create_async_engine` at import. Letting the validator do the conversion is
   both a fix and a simplification.
4. **Plain-Redis support in `src/core/redis.py`.** When
   `UPSTASH_REDIS_REST_URL`/`TOKEN` are both set (production), the Upstash REST
   adapter is used exactly as before. When they are empty, the client is built
   from `REDIS_URL` (e.g. the local `redis` service) via `redis.asyncio`. The
   method surface (`get`/`set`/`setex`/`ping`/`delete`/`incr`/`expire`/`eval`)
   matches, so `src/core/redis.py` needs no per-call changes and tests keep
   patching `redis_client` with fakeredis unchanged.
5. **Keep the real secrets required**: `SECRET_KEY` has *no* compose default —
   `${SECRET_KEY:?SECRET_KEY must be set (see docker/.env.example)}` fails fast
   at interpolation when the var is missing, in dev and production alike. A
   checked-in `docker/.env.example` documents the production set (`SECRET_KEY`,
   `OPENAI_API_KEY`, `HF_TOKEN`, `NEW_RELIC_LICENSE_KEY`, Upgrade credentials)
   and the one-liner for generating a key (`python -c 'import secrets;
   print(secrets.token_urlsafe(64))'`). `OPENAI_API_KEY`/`HF_TOKEN` default to
   empty — the app is fail-open on LLM calls — so dev boots without keys.
6. **README** documents `docker compose --profile dev up --build` as the
   one-command boot (and fixes the `docker-compose` → `docker compose` incantation).

## Consequences

### Gold

- **`docker compose --profile dev up --build` boots the whole app for real
  from `docker/.env.example`** — the "reproducible environment" claim now holds
  with one `cp` plus one edit (`SECRET_KEY` is deliberately the one var with no
  default).
- Production shape is untouched: without `--profile dev` no local datastore
  runs, and any explicit env var still overrides a default.
- `REDIS_URL` finally does what its name always implied, and the async-DB-URI
  double-interpolation footgun is gone.
- Healthchecks + `depends_on` ordering are orthogonal to the profile decision,
  so the stack is self-ordering when the profile is on.

### Trade-offs

- `SECRET_KEY` now fails compose startup when unset, so the first
  `cp docker/.env.example .env` must be followed by a real key. That is one
  extra step for a brand-new dev (previously a weak key booted the stack),
  accepted because a baked-in weak default was itself a footgun: deploying the
  stack as-is produced a trivial-signature JWT oracle.
- Upstash remains the production Redis path; the plain-Redis branch is only
  exercised in dev/CI until someone runs the app against a self-hosted Redis —
  `src/core/redis.py` tests (fakeredis) cover the surface, but not a real
  `redis:7` box outside the load gate. The CI load-test job now does run the
  app against a real Redis (`performance-loadtest`), which closes most of that
  gap.