# ADR-0003: A/B testing — in-app shadow / traffic-split, no external feature-flag service

- **Status**: Accepted
- **Date**: 2026-10-11

## Context

The ML service (image classification of civic issues) needs a way to test a
challenger model against the production champion before deciding whether to
promote it. The options considered:

1. **An external feature-flag / experiment service** (LaunchDarkly, Flagsmith,
   PostHog, ...) — powerful, but a new account + SDK + network dependency for a
   single boolean experiment, and the decision traffic would leave the app.
2. **Server-side orchestration in Prefect** (the repo already has Prefect) —
   appropriate for batch evaluation, wrong for per-request routing: a request
   cannot await an orchestration round-trip to decide which model to run.
3. **In-app A/B utility** — both modes live in the service, driven by settings.

The existing `src/ml/inference/ab_testing.py` already implemented modes and
bookkeeping (shadow + traffic split, per-request champion/challenger results,
counters). It was, however, **not wired into the inference path**: `predict_issue`
always used the plain predictor, and only `/ml/ab-test/stats` exposed the
tester. The A/B code therefore documented an intent it did not deliver.

## Decision

Keep A/B testing as an **in-app utility** (`ABTestPredictor` in
`backend/src/ml/inference/ab_testing.py`) driven by settings, with no external
feature-flag dependency:

- `AB_TEST_ENABLED` (default `false`) — switches the whole thing off; the
  default path must be byte-for-byte what ran before.
- `AB_TEST_MODE` (default `shadow`) — `shadow` runs the challenger alongside
  the champion and always serves the champion's prediction; `traffic_split`
  routes `AB_TEST_TRAFFIC_PCT` (default 10%) of requests to the challenger.
- The singleton is `ABTestPredictor` via `get_ab_tester()`, which reads the
  settings; challenger models are conventional files
  (`model_challenger.pth` / `.onnx` in the models dir).
- Deterministic, stable bucketing is a design target: in `traffic_split` the
  split uses the request's stable identity so the same request consistently
  sees the same variant (shadow mode requires no bucketing at all). The current
  implementation uses a per-request random roll, which is sufficient for a
  traffic-split experiment and documented as a candidate for a hash-based
  bucket keyed on issue id for within-request consistency.

Accepted explicitly as a **known limitation**: the predictor is wired to
`/ml/ab-test/stats` (observability of the test) and to tests, but rolling it
into `predict_issue`'s hot path is a staged follow-up, gated behind
`AB_TEST_ENABLED` so default behavior is untouched. The ADR records the
decision and the rollout order rather than pretending the wiring exists.

## Consequences

### Gold

- Zero new infrastructure: the experiment runs in-process, works offline, and
  costs nothing when disabled.
- Shadow mode lets a challenger be exercised against real traffic with zero
  user-visible risk; promotion decisions rest on `stats` + the evaluation
  harness (`scripts/evaluate_ml.py`), not on guesswork.
- The settings surface is small and deployment-friendly (env vars), matching
  how config is already managed.

### Trade-offs

- **Not yet in the request path.** Until the `predict_issue` wiring lands
  (tracked as the follow-up), A/B is a library + stats endpoint, not a live
  experiment. Documenting that explicitly is the honest state of the world.
- Traffic-split fidelity depends on the bucketing function; the current random
  roll cannot guarantee a given user/issue always sees the same variant. If a
  future experiment needs that guarantee, hash-based bucketing is the change.
- `log_to_db` exists on the config but persistence of AB results is not yet
  implemented — counters are in-process only, so stats reset on restart. Fine
  for experiments, wrong for long-running production measurement; noted as a
  follow-up rather than silently claimed.