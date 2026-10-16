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
  file-backed queue that survives a sink outage;
* the Grafana fan-out is an opt-in overlay, absent from the default config, so
  enabling it can never be a prerequisite for starting up.
"""

from __future__ import annotations

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
COLLECTOR_CONFIG = REPO_ROOT / "docker" / "otel-collector-config.yaml"
GRAFANA_OVERLAY = REPO_ROOT / "docker" / "otel-collector-config.grafana.yaml"
COMPOSE_FILE = REPO_ROOT / "docker" / "docker-compose.yml"

# The one line the collector actually runs by default (docker-compose command).
DEFAULT_CONFIG_FLAG = "--config=/etc/otelcol-contrib/config.yaml"


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
