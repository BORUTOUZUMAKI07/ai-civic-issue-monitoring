# ADR-0002: Race-safe ML model loading (eager warmup + double-checked locking)

- **Status**: Accepted
- **Date**: 2026-10-11

## Context

The backend serves on a single async event loop (uvicorn, one worker). Model
inference runs synchronously — the ~9 MB `model.onnx` / `model.pth` load plus
PyTorch/ONNX forward passes — from inside `asyncio.to_thread` worker threads so
the loop stays responsive.

Before this change the model was loaded lazily on the first inference request,
with three problems:

1. **First-request latency spike.** The first `POST /issues/upload` after boot
   paid the full model-load cost inline (~100 ms+ of CPU and I/O) on top of the
   inference, while the health probe still reported "healthy".
2. **Unbounded concurrent loads.** Two (or N) first uploads landing together
   each ran their own `_load_model()`, because the check-then-load was not
   atomic. Each load materialized a full model copy in RAM. Under a stampede
   this can be dozens of copies of a 9 MB artifact in one process.
3. **No tie to the boot sequence.** Nothing guaranteed the model was warm
   before traffic arrived.

Constraints on the fix:

- Loading must stay **fail-open** (a transient failure defers to the lazy
  path — never fail the request because warmup failed).
- When **no on-disk artifact exists** (fresh checkout, CI, test suites, the
  Docker image without a `dvc pull`), boot must **not** attempt to download
  weights: `build_model()` reaches `MobileNet_V2_Weights.DEFAULT` only in that
  no-artifact fallback path, and a boot-time download was unacceptable.
- The `asyncio.Lock` temptation was explicitly rejected: inference and loading
  run on `asyncio.to_thread` worker threads, and asyncio primitives are only
  safe on the event loop thread. The lock must be a thread primitive.

## Decision

`backend/src/ml/inference/predict.py` gains a module-level
`threading.Lock` (`_MODEL_LOAD_LOCK`) and **double-checked locking**: every load
site checks for an already-loaded model, takes the lock, re-checks, and only
then loads. Whichever thread wins the race loads once; the losers observe the
winner's model on the second check. The same lock covers model replacement, so
a concurrent reload cannot tear a half-built model into a reader.

A new `warmup_model()` (same file) is the boot-time entry point:

- If a model artifact exists on disk, load it under the lock (idempotent with
  the lazy path — a concurrent first request can't double-load).
- If **no** artifact exists, do nothing: the lazy path stays responsible, so a
  no-artifact environment boots without downloading anything.
- Any failure is caught and logged; the first real request falls back to lazy
  loading exactly as before.

`backend/src/main.py`'s lifespan calls
`await asyncio.to_thread(warmup_model)` during startup — warm the model in a
worker thread, never on the loop, and never let it block readiness.

## Consequences

### Gold

- The first upload (and every subsequent one) finds a preloaded model after a
  warm boot; the lazy path remains as a fail-open fallback.
- Concurrent first requests produce **one** model load, bounded RAM, and no
  reasoning about "who loaded first" in callers — the lock is the only place
  that matters.
- Artifact-absent environments (CI, tests, fresh clones) boot with no download
  and no model work at all, so the default dev/test loop stays fast.
- Testable deterministically: `TestWarmupModel` in `backend/tests/test_ml_inference.py`
  exercises warm-vs-empty, concurrent double-load prevention, and failure
  fallback without any real artifact.

### Trade-offs

- A `threading.Lock` guards CPU-bound loading across worker threads; if the
  app ever moves to a multi-process (gunicorn workers) deployment, each process
  still loads once — the guarantee is per-process, not per-cluster. A cross-
  process advisory lock (e.g. via Redis `SET NX`) would be the next step and is
  documented as such, not implemented.
- Warmup adds ~model-load time to *startup*, which trades first-request latency
  for boot latency. For a horizontally scaled API that is the right trade; for
  a serverless cold start it would want revisiting.
- `warmup_model()` deliberately does nothing without an artifact on disk —
  this means a deployment whose `dvc pull` ran *after* the app booted still
  relies on the lazy path. Accepted: the artifact must exist before boot.