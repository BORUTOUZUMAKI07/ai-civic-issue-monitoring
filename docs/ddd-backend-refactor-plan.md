# Backend DDD Restructure — Migration Plan

Status: **Executed** — structural restructure and route surgery complete and green on `refactor/ddd-backend`.
Scope: `backend/src/` only. No frontend, no ML/prefect, no dependency changes.

---

## 1. Goal

Move the backend from a *mixed* layout (flat `src/repositories/`, flat `src/models/`,
fat `domains/*/routes.py` with inline business logic, services that construct their own
repositories) to a **domain-per-package (vertical slice)** layout where each domain owns
its models, schemas, repositories, services and API layer, with dependencies pointing
inward (DIP) and no cross-domain reach-through.

This matches the structure of the reference projects the user cited:
`domain/{models, schemas, services, repositories, api}`.

---

## 2. Target structure

```
backend/src/
  main.py                         # app factory + router assembly ONLY
  core/                           # cross-cutting infra (kept, minor tidy)
    config.py  database.py  security.py  redis.py  mongodb.py
    observability.py  email.py  llm.py  embeddings.py  gate.py
    rbac.py  deps.py
  shared/                         # NEW — shared kernel, depends on nothing
    __init__.py
    base.py                       # SQLAlchemy Base (moved from models/base.py)
    errors/                       # moved from src/errors/
      __init__.py  base.py  auth.py  common.py  issue.py
  domains/
    issues/
      __init__.py
      models/issue.py             # Issue, IssueType, IssueStatus, ISSUE_TYPE_MAP
      schemas/{requests,responses}.py
      repositories/{ports.py, issue_repository.py}
      services/issue_service.py
      api/routes.py
    assignments/                  # NEW domain (Assignment is its own aggregate: lifecycle + SLA)
      models/assignment.py
      repositories/assignment_repository.py
      services/...
      api/... (admin endpoints stay where they are; this holds the aggregate + repo)
    resolution/
      models/resolution.py
      repositories/resolution_repository.py
      services/resolution_service.py
      api/routes.py
    engineers/
      models/engineer.py
      schemas/  repositories/engineer_repository.py  services/  api/routes.py
    wards/
      models/ward.py
      schemas/  repositories/ward_repository.py
      services/ward_service.py  geofencing.py  api/routes.py
    users/                        # NEW — owns User + UserRole (auth consumes it)
      models/user.py
      repositories/user_repository.py
    auth/
      oauth.py  password_reset.py  twofa.py  service.py  schemas.py  api/routes.py
    dashboard/  notifications/  ml/  admin/
  agents/                         # functional module (unchanged location)
  ml/                             # ML platform (unchanged)
  rag/                            # RAG (unchanged)
  middleware/                     # unchanged
  models/                         # KEPT AS THIN REGISTRY (see §4 constraints)
    __init__.py                   # imports every domain model to register mappers
    base.py                       # re-export of shared.base.Base
```

Not moving to per-domain: `agents/`, `ml/`, `rag/` — these are functional/platform
modules, not CRUD web domains. Moving them buys nothing and risks the ML gates.

---

## 3. Layering rules (what "SOLID / no tight coupling" means concretely)

| Layer | May import | Must NOT import |
|---|---|---|
| `shared` | stdlib, SQLAlchemy | `core`, `domains`, `agents`, `ml` |
| `core` | stdlib, `shared` | `domains` |
| `domains/<x>/models` | `shared` | other domains' internals |
| `domains/<x>/repositories` | own models, `shared` | other domains' repos |
| `domains/<x>/services` | own models/schemas/repos + **ports** | concrete repos of other domains |
| `domains/<x>/api` | own services/schemas | repositories directly |
| `main.py` | all `domains/*/api`, `core` | repositories/models |

Enforcement: a **pure-pytest architecture test** (no new dependency) that AST-walks
`src/domains` and asserts the import matrix above. Runs in `test-ci`.

---

## 4. Hard constraints discovered (must be respected)

1. **`backend/tests/conftest.py` is protected.** It does:
   - `import src.models` (registers SQLAlchemy mappers)
   - `from src.models.base import Base`
   Therefore `src.models` and `src.models.base` **must stay importable**. The plan keeps
   `src/models/__init__.py` as a registry aggregator (imports all domain models) and
   `src/models/base.py` as a one-line re-export of `shared.base.Base`. This is a
   *registry*, not duplication.
   *(Alternative, if the user prefers zero shims: unprotect conftest and change its two
   imports. Not assumed here.)*

2. **`backend/pyproject.toml`** keys two things by module path:
   - `[[tool.mypy.overrides]] module = [...]` — the strict-mode burn-down list. Every
     moved module must have its path updated or mypy flips to `strict` on it and fails.
   - `[tool.ruff.lint.per-file-ignores]` — `src/core/config.py` (N802) and
     `src/errors/**` (N818). If `errors/` moves to `shared/errors/`, update to
     `src/shared/errors/**`.

3. **ORM cross-domain relationships** use string lookups (`relationship("Ward")`,
   `relationship("Issue")`, …). They only resolve once *every* model module has been
   imported. The `src/models/__init__.py` aggregator + `import src.models` in conftest
   guarantees this. No per-domain `models/__init__.py` may be the *only* path used by
   the app; `main.py` (or the aggregator) must import all of them.

4. **URLs do not change.** `main.py` already mounts everything under `prefix="/api/v1"`.
   The frontend proxy allowlist and all clients are unaffected. This is purely internal.

5. **Gates must stay green at the end of every phase** (see §7).

---

## 5. File-move map (source → destination)

### 5.1 Repositories (flat → domain)
| From | To |
|---|---|
| `src/repositories/issue_repository.py` | `src/domains/issues/repositories/issue_repository.py` |
| `src/repositories/assignment_repository.py` | `src/domains/assignments/repositories/assignment_repository.py` |
| `src/repositories/resolution_repository.py` | `src/domains/resolution/repositories/resolution_repository.py` |
| `src/repositories/engineer_repository.py` | `src/domains/engineers/repositories/engineer_repository.py` |
| `src/repositories/ward_repository.py` | `src/domains/wards/repositories/ward_repository.py` |
| `src/repositories/user_repository.py` | `src/domains/users/repositories/user_repository.py` |
| `src/repositories/__init__.py` | deleted |

### 5.2 Models (flat → domain, except base)
| From | To |
|---|---|
| `src/models/base.py` | `src/shared/base.py` (+ `src/models/base.py` re-export shim) |
| `src/models/issue.py` | `src/domains/issues/models/issue.py` |
| `src/models/assignment.py` | `src/domains/assignments/models/assignment.py` |
| `src/models/resolution.py` | `src/domains/resolution/models/resolution.py` |
| `src/models/engineer.py` | `src/domains/engineers/models/engineer.py` |
| `src/models/ward.py` | `src/domains/wards/models/ward.py` |
| `src/models/user.py` | `src/domains/users/models/user.py` |
| `src/models/idempotency.py` | `src/domains/issues/models/idempotency.py` |
| `src/models/__init__.py` | rewritten as the registry aggregator |
| `src/models/__init__.py` `import` list | unchanged semantics (registers all) |

### 5.3 Errors
| From | To |
|---|---|
| `src/errors/*.py` | `src/shared/errors/*.py` (+ update ruff ignore path) |

### 5.4 Routes → api, schemas split
| From | To |
|---|---|
| `src/domains/*/routes.py` | `src/domains/*/api/routes.py` |
| `src/domains/*/schemas.py` | `src/domains/*/schemas/` (split requests/responses where ≥2 DTOs) |
| `src/domains/*/service.py` | `src/domains/*/services/<name>_service.py` |

---

## 6. Import-update worklist (who imports what today)

Bounded set — verified with ripgrep:

- **Repositories consumers** (must be repointed): `core/deps.py`,
  `domains/issues/service.py`, `domains/engineers/service.py`, `domains/wards/service.py`,
  `domains/resolution/routes.py`, `domains/auth/{oauth,password_reset,service,twofa}.py`,
  `repositories/__init__.py`.
- **Models consumers**: `agents/{matching,analytics}.py`, `core/rbac.py`,
  `middleware/rbac.py`, `rag/retrieval.py`, all repositories, and most domains.
- **Tests importing internals directly** (editable — conftest excluded):
  `test_models.py`, `test_taxonomy.py`, `test_rbac.py`, `test_refresh_rotation.py`,
  `test_idempotency_api.py`, `test_hypothesis.py`, `test_oauth_password_reset.py`.
  These get updated to the new paths in the same phase as the move.
- **`main.py`**: the 9 `include_router` imports get the new `api/` paths.

---

## 7. Execution phases (each ends green + a commit)

**Phase 0 — Freeze current work.**
Commit + push the finished photo-upload + notification-bell + `/engineers/me` work so the
refactor sits on a clean base and is trivially revertible.

**Phase 1 — Shared kernel + ports (no moves).**
- Add `src/shared/base.py`; make `src/models/base.py` re-export it.
- Move `src/errors/` → `src/shared/errors/`; update ruff ignore path; update importers.
- Add `repositories/ports.py` Protocols per domain and have services depend on the
  Protocol, not the concrete class (constructor injection with a default factory).
- Add the architecture test.
- Green: lint, mypy, test-ci.

**Phase 2 — Repositories move (one domain per commit).**
Order: issues → assignments → resolution → engineers → wards → users.
Update the consumer list each time. Green after each.

**Phase 3 — Models move (one domain per commit).**
Same order. After each, rewrite `src/models/__init__.py` aggregator + update editable
tests. Run the full suite (mapper configuration is the risky part). Green after each.

**Phase 4 — Fat-route surgery.**
- `domains/admin/routes.py` (237 lines) and `domains/issues/routes.py` (561 lines):
  extract inline SQL/`select()` and business rules into the domain service.
- Routes become thin controllers: validate DTO → call service → return schema.
- Green after each.

**Phase 5 — `routes.py` → `api/routes.py`; schemas split.**
Mechanical rename + import fixes. Green.

**Phase 6 — Tooling sync + full gate run.**
- Update `pyproject.toml` mypy override module paths and ruff per-file-ignores.
- Run the complete backend gate suite:
  `pixi run lint`, `pixi run typecheck`, `pixi run test-ci`, `pixi run security`,
  `pixi run security-audit`, `pixi run secret-scan`.
- Commit + push.

**Phase 7 (optional) — Second domain exemplar review.**
Confirm the pattern reads well across ≥3 domains before declaring done.

---

## 8. Rollback

Each phase is an independent commit on `main` (or a feature branch — see open question).
Any phase that fails its gates is `git revert`ed; earlier phases remain valid because the
app never had a broken intermediate state.

---

## 9. Risks & mitigations

| Risk | Mitigation |
|---|---|
| SQLAlchemy mapper configuration breaks (string relationships) | `src/models/__init__.py` aggregator imported everywhere; full suite run after each model move |
| Protected `conftest.py` needs `src.models` / `src.models.base` | Keep them as registry + re-export shim (§4.1) |
| mypy strict flips on stray moved modules | Update `pyproject.toml` overrides in the same commit as the move |
| Circular imports (bit us in the earlier attempt) | Strict layering + build bottom-up (`shared` → `core` → models → repos → services → api); never import upward |
| Large diff hard to review | One domain per commit; ~10–14 focused commits |

---

## 10. Definition of done

- Target tree in §2 exists; no flat `src/repositories/`; models/repos live in domains.
- Architecture test enforces the §3 matrix and passes.
- `pixi run lint && typecheck && test-ci && security && security-audit && secret-scan` all green.
- No URL/behavior change — API contract identical.
- `git log` shows one reviewable commit per phase.

---

## 11. Decisions (agreed)

1. **Branch:** work on `refactor/ddd-backend`; merge to `main` only when all phases + gates
   are green at the end.
2. **`src/models/` shim:** keep the registry aggregator (`__init__.py`) + `base.py`
   re-export. This respects the protected `conftest.py` and is required for mapper
   registration regardless.
3. **Phase 4 scope:** all routes — extract inline SQL/business logic from
   `admin`, `issues`, `dashboard`, `notifications`, `ml` into services.
4. **Sequencing note:** Phase 4 was executed *after* Phase 5. Introducing repository
   ports before the repository move would have meant moving them twice, so the
   structural moves (repos → models → api/services) came first, followed by the
   ports + constructor injection refinement.

---

## 12. Execution status

**Done (all on `refactor/ddd-backend`, gates green after each commit):**

| Phase | Commit | Result |
|---|---|---|
| 0 | `9cf7d83` (main) | photo-upload resolution + notification bell committed & pushed to `main` |
| 1 | `39f2f89` | `shared/` kernel (Base + `errors/`) + architecture layering test |
| 2 | `a4e7f2b` | repositories → `domains/*/repositories/`; new `assignments` + `users` domains |
| 3 | `aa59000` | ORM models → `domains/*/models/`; `src/models/` registry; role hierarchy → `users` |
| 5 | `17c82d2` | routers → `domains/*/api/routes.py`; services → `domains/*/services/` |
| 4 | route surgery | thin routers; business logic moved into services/repositories/schemas |

Every domain now has `models/  repositories/  services/  api/  (+ schemas.py)`.
`core/` and `shared/` are enforced as layering leaves by `tests/test_architecture.py`.

**Phase 4 — route surgery (done):** the fat routers are now thin
HTTP shells; the logic lives in services/repositories/schemas:

- `users/services/user_service.py` — `list_users`, `change_role` (the role-swap rules)
- `issues/services/issue_service.py` — `list_review_queue`, `get_assignment_map`,
  `review_issue`
- `engineers/services/engineer_service.py` — `create_engineer`, `get_my_profile`,
  `list_my_assignments`
- `AssignmentRepository.latest_by_issue_ids` / `list_by_engineer_with_issue` and
  `IssueRepository.list_review_queue` / `count_review_queue` (SQL back in the data layer)
- `UserRepository.list_filtered` / `count_filtered`
- `IssueResponse.from_issue`, `EngineerResponse.from_engineer` (response mappers)
- one shared `users.rbac.require_admin` replaces the `_require_admin` copy in three routers

`dashboard`, `notifications` and `ml` routers were already thin pass-throughs, so no change.

**Ports + dependency inversion (done):** every domain that owns a repository now exposes
a `repositories/ports.py` `Protocol` (`IssueRepositoryPort`, `AssignmentRepositoryPort`,
`EngineerRepositoryPort`, `UserRepositoryPort`, `WardRepositoryPort`,
`ResolutionRepositoryPort`). The services depend on the Protocol — `IssueService`,
`UserService`, `EngineerService`, `WardService` accept optional `*_repo=` keyword
arguments typed with the port and fall back to the concrete repository when omitted, so
production wiring is unchanged while tests can inject in-memory fakes. New
`tests/test_domain_services_unit.py` exercises the pure service methods, the response
mappers and `require_admin` with fakes and no database.

**Verification:** `pixi run lint`, `pixi run typecheck`, and the full pytest suite
(206 passed / 1 skipped) are green; `security` reports 0 issues and `security-audit`
exits 0. `pixi.lock` was intentionally excluded from all commits (it auto-refreshes when
tasks run and is unrelated to this refactor).
