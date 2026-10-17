"""Guards for the tracked Layer-2 collector configs (static, no Docker).

Why these exist: a collector that refuses to build its own config exits 1 before
``/healthz`` ever answers, and the only symptom a human sees downstream is an
empty New Relic — which is indistinguishable from an app that emitted nothing
(configured-but-broken). Nothing here starts Docker: these assert over the YAML
that ships, so they run in the default CI environment on every push.

``otelcol validate`` is deliberately not used as the guard. Measured against the
historical defect (an empty ``action:`` on a resource attribute), validate exits
0 — it only unmarshals and never builds the component graph, which is exactly
where the rejection happened. Static assertions name the offending key instead
of reporting "the collector did not start".

What is pinned:
* the resource-processor footgun that kills startup (every attribute declares an
  action);
* the receiver handshake — both OTLP protocols require basic auth, the
  credential comes from the environment, and the app and the collector are
  handed the *same* pair (the app half is asserted in
  ``test_observability_3layer.py``);
* one OTLP receiver for all three signals, no Prometheus scrape path, and the
  file-backed queue that survives a sink outage — including the image that
  pre-creates the queue directory for the collector uid, so a fresh volume
  cannot kill the collector at startup;
* the tail-sampling intent — errors and slow traces kept, ~10% of the rest —
  including that the error policy lists only ``ERROR``: adding ``UNSET`` (a
  healthy span's default status) matches almost every trace and quietly ships
  the whole stream to the free tier;
* the built image actually BOOTS on a freshly created named volume — a
  Docker-marked integration test (``Backend Integration`` in CI), because shape
  assertions cannot see a queue directory the collector refuses to write to;
* the Grafana fan-out is an opt-in overlay, absent from the default config, so
  enabling it can never be a prerequisite for starting up.
"""

from __future__ import annotations

import shutil
import subprocess
import time
import uuid
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
COLLECTOR_CONFIG = REPO_ROOT / "docker" / "otel-collector-config.yaml"
GRAFANA_OVERLAY = REPO_ROOT / "docker" / "otel-collector-config.grafana.yaml"
COLLECTOR_DOCKERFILE = REPO_ROOT / "docker" / "otel-collector.Dockerfile"
COMPOSE_FILE = REPO_ROOT / "docker" / "docker-compose.yml"

# The collector image runs as this uid; the queue dir must be owned by it.
COLLECTOR_UID = "10001:10001"

# The one line the collector actually runs by default (docker-compose command).
DEFAULT_CONFIG_FLAG = "--config=/etc/otelcol-contrib/config.yaml"

# The two FROM images in docker/otel-collector.Dockerfile: the collector
# itself, and the shell-ful busybox stage that pre-creates the queue directory
# (the distroless collector image has no shell to mkdir with).
BASE_IMAGES = (
    "busybox:stable",
    "otel/opentelemetry-collector-contrib:0.121.0",
)

# Readiness lands ~1s after start (measured); a rejected config, or a queue
# directory the collector cannot write to, exits immediately. Poll for the
# marker so a healthy run is quick and a broken one fails fast.
STARTUP_TIMEOUT_SECONDS = 30.0
POLL_INTERVAL_SECONDS = 0.5
READY_MARKER = "Everything is ready"


def _load(path: Path) -> dict:
    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(config, dict), f"{path} did not parse into a mapping"
    return config


def _env_map(environment: object) -> dict[str, str]:
    """Flatten a compose `environment` (list of ``K=V`` or a mapping) to a dict."""
    if isinstance(environment, dict):
        return {str(k): str(v) for k, v in environment.items()}
    assert isinstance(environment, list), f"unexpected compose environment: {environment!r}"
    parsed: dict[str, str] = {}
    for entry in environment:
        key, _, value = str(entry).partition("=")
        parsed[key] = value
    return parsed


def test_every_resource_attribute_declares_an_action() -> None:
    """The known startup killer, named rather than inferred from a dead collector.

    Omitting ``action`` yields an empty action and the processor refuses to
    build (``failed to create "resource" processor ... unsupported action ""``),
    which exits 1 before health ever becomes observable.
    """
    config = _load(COLLECTOR_CONFIG)
    resource = (config.get("processors") or {}).get("resource")
    assert resource, "processors.resource is missing"
    attributes = resource.get("attributes") or []
    assert attributes, "processors.resource.attributes is empty"
    for entry in attributes:
        assert entry.get("action"), (
            f"resource attribute {entry.get('key')!r} has no `action`; the "
            "collector-contrib processor rejects an empty action at startup"
        )


def test_otlp_receiver_requires_basic_auth_on_both_protocols() -> None:
    """An unauthenticated receiver on a public port burns the ingest quota free."""
    config = _load(COLLECTOR_CONFIG)
    protocols = config["receivers"]["otlp"]["protocols"]
    for protocol in ("grpc", "http"):
        assert protocols[protocol]["auth"]["authenticator"] == "basicauth/server", (
            f"the {protocol} receiver must be gated by basicauth/server"
        )
    # Declaring the extension without registering it is an equally silent gap.
    assert "basicauth/server" in config["service"]["extensions"]


def test_receiver_credentials_are_environment_driven() -> None:
    """No literal credential may sit in the tracked config, and both halves of the
    stack must read the same environment variable names the app sends."""
    config = _load(COLLECTOR_CONFIG)
    extension = config["extensions"]["basicauth/server"]
    inline = extension["htpasswd"]["inline"]
    assert inline == "${env:OTLP_AUTH_USER}:${env:OTLP_AUTH_PASSWORD}", (
        "the htpasswd entry must come from OTLP_AUTH_USER/OTLP_AUTH_PASSWORD "
        "so the app and the collector cannot drift; a literal would put a "
        "credential in version control"
    )


def test_compose_hands_the_same_credential_to_app_and_collector() -> None:
    """End-to-end wiring: the app authenticates against the receiver that demands it.

    An empty collector-side default would mean "require a credential the app is
    never given", i.e. every signal silently 401s.
    """
    compose = _load(COMPOSE_FILE)
    services = compose["services"]
    backend_env = _env_map(services["backend"]["environment"])
    collector_env = _env_map(services["otel-collector"]["environment"])

    for variable in ("OTLP_AUTH_USER", "OTLP_AUTH_PASSWORD"):
        assert variable in collector_env, f"the collector must read {variable}"
        assert variable in backend_env, f"the backend must send {variable}"
        assert backend_env[variable] == collector_env[variable], (
            f"{variable} differs between app and collector — the OTLP handshake "
            "would fail with a 401 and a quietly empty sink"
        )
        assert backend_env[variable], f"{variable} must not default to empty"


def test_three_signals_one_receiver_and_no_prometheus_scrape() -> None:
    """ADR-0007: OTLP is the only transport, so nothing can be scraped-only."""
    config = _load(COLLECTOR_CONFIG)
    pipelines = config["service"]["pipelines"]
    assert set(pipelines) == {"logs", "metrics", "traces"}
    for name, pipeline in pipelines.items():
        assert pipeline["receivers"] == ["otlp"], f"{name} must read the single OTLP receiver"
        assert "otlphttp/newrelic" in pipeline["exporters"], f"{name} must reach the primary sink"
        assert not any("prometheus" in e for e in pipeline["exporters"]), (
            f"{name} must not carry a Prometheus scrape path"
        )
    assert not any(
        key.startswith("prometheus") for key in config.get("exporters", {})
    ), "no Prometheus exporter may be declared"


def test_primary_sink_queues_to_disk_and_retries() -> None:
    """Survivability: a sink outage must not drop telemetry once retries expire."""
    config = _load(COLLECTOR_CONFIG)
    exporter = config["exporters"]["otlphttp/newrelic"]
    assert exporter["sending_queue"]["enabled"] is True
    assert exporter["sending_queue"]["storage"] == "file_storage"
    assert exporter["retry_on_failure"]["enabled"] is True
    assert "file_storage" in config["service"]["extensions"]


def test_tail_sampling_keeps_errors_and_a_sample_of_the_rest() -> None:
    """The quota guard: the error policy must NOT match every healthy span.

    ``status_code`` accepts ``OK``/``ERROR``/``UNSET``, and ``UNSET`` is the
    default status of a span that simply succeeded. Listing it makes the policy
    match nearly every trace, so the policy "samples" them all and
    ``sample-rest`` never drops anything — the collector then ships the ENTIRE
    trace stream to the (free-tier) sink, silently. Naming only ``ERROR`` is
    what makes "errors + ~10% of the rest" true, and the latency policy keeps
    the slow traces that a healthy status would otherwise hide.
    """
    config = _load(COLLECTOR_CONFIG)
    tail_sampling = config["processors"]["tail_sampling"]
    policies = {policy["name"]: policy for policy in tail_sampling["policies"]}

    errors = policies["keep-all-errors"]
    assert errors["type"] == "status_code"
    assert errors["status_code"]["status_codes"] == ["ERROR"], (
        "the status_code policy must list only ERROR: UNSET is the default "
        "status of a healthy span, so [ERROR, UNSET] matches almost every "
        "trace and silently disables the probabilistic sampling of the rest"
    )

    slow = policies["keep-slow"]
    assert slow["type"] == "latency"
    assert slow["latency"]["threshold_ms"] == 2000, (
        "the latency policy must keep traces slower than 2s — a healthy "
        "status would otherwise let a slow-but-successful trace be dropped"
    )

    rest = policies["sample-rest"]
    assert rest["type"] == "probabilistic"
    assert rest["probabilistic"]["sampling_percentage"] == 10

    # Tail sampling buffers whole traces, so it belongs on traces only: logs and
    # metrics have no trace to sample and attaching it there is a config error.
    pipelines = config["service"]["pipelines"]
    assert "tail_sampling" in pipelines["traces"]["processors"]
    for name in ("logs", "metrics"):
        assert "tail_sampling" not in pipelines[name]["processors"], (
            f"{name} has no trace to sample; attaching tail_sampling is a configuration error"
        )


def test_collector_image_precreates_the_queue_dir_for_its_uid() -> None:
    """The startup trap Nexus documented, guarded statically.

    ``file_storage`` writes to ``/var/lib/otelcol/queue``, but the collector
    image is distroless (no shell) and ``create_directory: true`` cannot mkdir
    under an unwritable ``/var/lib``. A fresh named volume inherits the
    *image's* ownership at that path: root-owned means the collector (uid
    10001) exits at startup with ``open .../exporter_otlphttp_newrelic_*:
    permission denied`` — no ``/healthz``, and the only downstream symptom is
    a quietly empty sink. The fix is a builder stage that pre-creates the
    directory with the collector's uid.
    """
    dockerfile = COLLECTOR_DOCKERFILE.read_text(encoding="utf-8")
    assert "busybox:stable AS queuedir" in dockerfile, (
        "the queue directory must be created in a shell-ful builder stage: "
        "the collector image itself has no shell to mkdir with"
    )
    assert "RUN mkdir -p /var/lib/otelcol/queue" in dockerfile
    copy_line = (
        f"COPY --from=queuedir --chown={COLLECTOR_UID} /var/lib/otelcol /var/lib/otelcol"
    )
    assert copy_line in dockerfile, (
        "the queue dir must ship owned by the collector uid so a fresh named "
        "volume inherits a writable ownership"
    )


def test_compose_builds_the_collector_image_and_mounts_the_queue() -> None:
    """Wiring: an orphaned Dockerfile protects nothing.

    Compose must *build* the repo image (pulling the bare upstream one
    re-opens the permission-denied startup failure), and the volume must land
    exactly on ``file_storage.directory`` — a mismatched target would mount
    the queue somewhere the pre-created ownership never applies.
    """
    compose = _load(COMPOSE_FILE)
    collector = compose["services"]["otel-collector"]

    build = collector.get("build") or {}
    assert build.get("dockerfile") == "otel-collector.Dockerfile", (
        "compose must build the repo's collector image, which pre-creates the "
        "queue directory; the bare upstream image leaves it root-owned and "
        "the collector exits at startup"
    )
    assert str(collector.get("image", "")).endswith("civicpulse-otel-collector:local"), (
        "the built image must be tagged as the local one compose runs"
    )

    queue_dir = _load(COLLECTOR_CONFIG)["extensions"]["file_storage"]["directory"]
    targets = [str(entry).partition(":")[2].split(":")[0] for entry in collector["volumes"]]
    assert queue_dir in targets, (
        f"the otelcol-queue volume must mount at {queue_dir} — the directory "
        "the Dockerfile pre-creates and file_storage writes to"
    )


def test_grafana_fan_out_is_opt_in_and_complete() -> None:
    """Two properties that must hold *together*.

    The overlay must be complete enough to actually fan out when loaded, and the
    base config must not reference it at all — because an otlphttp exporter with
    an empty endpoint stops the collector from starting, so a default-on sink
    would make the stack unbootable for anyone without Grafana credentials.
    """
    assert GRAFANA_OVERLAY.exists(), "the fan-out overlay must ship alongside the base config"

    overlay = _load(GRAFANA_OVERLAY)
    exporter = overlay["exporters"]["otlphttp/grafana"]
    assert exporter["endpoint"] == "${env:GRAFANA_OTLP_ENDPOINT}"
    assert exporter["headers"]["authorization"] == "${env:GRAFANA_OTLP_TOKEN}"
    # Same durability as the primary sink: a slow second sink must not lose data
    # or block New Relic.
    assert exporter["sending_queue"]["storage"] == "file_storage"
    assert exporter["retry_on_failure"]["enabled"] is True

    overlay_pipelines = overlay["service"]["pipelines"]
    assert set(overlay_pipelines) == {"logs", "metrics", "traces"}
    for name, pipeline in overlay_pipelines.items():
        assert "otlphttp/newrelic" in pipeline["exporters"], f"overlay {name} must keep New Relic"
        assert "otlphttp/grafana" in pipeline["exporters"], f"overlay {name} must add Grafana"
        # The tail-sampling decision must not change just because a sink joined.
        if name == "traces":
            assert "tail_sampling" in pipeline["processors"]

    # ...and the default config must not depend on those credentials existing.
    base = _load(COLLECTOR_CONFIG)
    assert "otlphttp/grafana" not in base.get("exporters", {}), (
        "the base config must not declare the Grafana exporter: it is only "
        "valid once GRAFANA_* credentials exist, and an empty endpoint stops "
        "the collector from starting at all"
    )
    for name, pipeline in base["service"]["pipelines"].items():
        assert "otlphttp/grafana" not in pipeline["exporters"], (
            f"base pipeline {name} must not fan out by default"
        )


def test_default_command_runs_only_the_base_config() -> None:
    """The overlay is mounted but not loaded — enabling it stays a deliberate act."""
    compose = _load(COMPOSE_FILE)
    collector = compose["services"]["otel-collector"]
    command = collector["command"]
    assert command == [DEFAULT_CONFIG_FLAG], (
        f"the default collector command changed: {command!r}. Loading the "
        "Grafana overlay by default would require credentials the stack may "
        "not have."
    )
    mounts = [str(v) for v in collector["volumes"]]
    assert any("otel-collector-config.yaml:" in m for m in mounts), "base config must be mounted"
    assert any("otel-collector-config.grafana.yaml:" in m for m in mounts), (
        "the overlay should be pre-mounted so enabling it is only a command flag"
    )


# ──────────────── the Docker half: the image must actually boot ────────────────
#
# Everything above asserts the *shape* of the tracked files. This section runs
# the built image, because the failure this repo actually hit — a queue
# directory the collector (uid 10001) could not write to — is invisible to any
# amount of YAML inspection: `otelcol validate` passes on it, and so does every
# static guard above. It only exists once the image runs against a volume.


def _docker(args: list[str], timeout: float = 60) -> subprocess.CompletedProcess[str]:
    """Run a docker subcommand, capturing both streams as text.

    ``encoding``/``errors`` match the rest of the suite: on Windows the child's
    output is not reliably UTF-8, and a decode error here would look like a
    Docker failure rather than a decode problem.
    """
    return subprocess.run(
        ["docker", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
    )


def _require_docker() -> None:
    """Skip — never fail — when Docker (or the network) cannot supply a run.

    A missing daemon is an environment, not a regression: going red because
    Docker Desktop is off would teach people to ignore the signal that matters.
    """
    if shutil.which("docker") is None:
        pytest.skip("docker is not on PATH; the collector startup check needs it")

    try:
        probe = _docker(["info"], timeout=30)
    except (OSError, subprocess.SubprocessError) as exc:
        pytest.skip(f"docker is not runnable: {type(exc).__name__}: {exc}")
    if probe.returncode != 0:
        pytest.skip("docker daemon is not running (environment, not a regression)")

    # Build FROM these; the collector image is large. Pull only what is missing,
    # and skip (with the reason) when the network cannot supply it — "no image"
    # is not "the collector is broken".
    for image in BASE_IMAGES:
        if _docker(["image", "inspect", image], timeout=60).returncode == 0:
            continue
        try:
            pull = _docker(["pull", image], timeout=600)
        except (OSError, subprocess.SubprocessError) as exc:
            pytest.skip(f"cannot pull {image}: {type(exc).__name__}: {exc}")
        if pull.returncode != 0:
            pytest.skip(f"cannot pull {image}: {pull.stderr.strip()[:300]}")


def _wait_until_ready(name: str) -> str | None:
    """Poll the container; ``None`` means readiness, else a failure reason.

    Readiness is the property under test, not liveness: the collector prints
    the marker only *after* every pipeline is built AND the ``file_storage``
    queue is writable, which is the step a root-owned volume used to reject at
    startup with ``permission denied``.
    """
    deadline = time.monotonic() + STARTUP_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        state = _docker(
            ["inspect", name, "--format", "{{.State.Running}}|{{.State.ExitCode}}"],
            timeout=30,
        )
        running, _, exit_code = state.stdout.strip().partition("|")
        if running != "true":
            return f"the collector exited with code {exit_code} instead of reaching readiness"

        logs = _docker(["logs", name], timeout=30)
        if READY_MARKER in logs.stdout + logs.stderr:
            return None
        time.sleep(POLL_INTERVAL_SECONDS)

    return f"no readiness line after {STARTUP_TIMEOUT_SECONDS:.0f}s"


def _tail(name: str, lines: int = 25) -> str:
    """Last ``lines`` of the container's output, for the failure message."""
    logs = _docker(["logs", name], timeout=30)
    combined = (logs.stdout + logs.stderr).splitlines()
    return "\n".join(combined[-lines:])


@pytest.mark.integration
@pytest.mark.timeout(600)
def test_the_collector_image_boots_on_a_fresh_named_volume() -> None:
    """The integration half: the image we ship starts on an empty volume.

    Reproducer for the defect fixed in PR #7. Compose ran the *bare upstream*
    image, so the queue directory did not exist / was not writable by the
    collector uid (10001). A fresh named volume inherits the *image's* ownership
    at the mount path, so the collector exited at startup with::

        open /var/lib/otelcol/queue/exporter_otlphttp_newrelic_traces: permission denied

    Building the repo image and booting it on a genuinely fresh volume is the
    only assertion that covers that class of failure.

    Deliberately unlike Nexus's boot test: that one mounts a world-writable
    ``--tmpfs`` at the storage path, which *masks* this ownership bug. Here the
    volume is a real, empty, image-initialised named volume, and no ports are
    published (a host already running a collector must not collide).
    """
    _require_docker()

    suffix = uuid.uuid4().hex[:8]
    image = f"civicpulse-otel-collector-test:{suffix}"
    container = f"civicpulse-cfg-check-{suffix}"
    volume = f"civicpulse-cfg-check-{suffix}"

    build = _docker(
        ["build", "-f", str(COLLECTOR_DOCKERFILE), "-t", image, str(COLLECTOR_DOCKERFILE.parent)],
        timeout=600,
    )
    assert build.returncode == 0, f"docker build failed for {COLLECTOR_DOCKERFILE}:\n{build.stderr.strip()}"

    failure: str | None = None
    logs = ""
    try:
        started = _docker(
            [
                "run",
                "-d",
                "--name",
                container,
                # A brand-new named volume: empty, and root-owned until the
                # image's COPY --chown seeds it. This is the whole point — no
                # --tmpfs, no bind mount, no chown to hide the bug.
                "-v",
                f"{volume}:/var/lib/otelcol/queue",
                # The config reads these via ${env:...}; an unset name is an
                # error for the collector, so supply them exactly as
                # docker-compose.yml does.
                "-e",
                "ENVIRONMENT=development",
                "-e",
                "SERVICE_VERSION=dev",
                "-e",
                "OTLP_AUTH_USER=civicpulse",
                "-e",
                "OTLP_AUTH_PASSWORD=civicpulse",
                "-e",
                "NEW_RELIC_LICENSE_KEY=not-set",
                image,
                DEFAULT_CONFIG_FLAG,
            ],
            timeout=120,
        )
        assert started.returncode == 0, f"docker run failed:\n{started.stderr.strip()}"

        failure = _wait_until_ready(container)
        if failure is not None:
            logs = _tail(container)
    finally:
        # Always clean up: the names are unique, so a leak collides with
        # nothing, but a rejected config left alive would confuse whoever looks
        # at `docker ps` next.
        _docker(["rm", "-f", container], timeout=60)
        _docker(["volume", "rm", volume], timeout=60)
        _docker(["image", "rm", "-f", image], timeout=60)

    assert failure is None, (
        f"{failure} — the built collector image must start on a fresh volume "
        f'(readiness marker: "{READY_MARKER}"). A root-owned queue directory '
        "surfaces here as `permission denied`.\n"
        f"--- collector log (tail) ---\n{logs}"
    )
