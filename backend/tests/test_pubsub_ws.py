"""Redis pub/sub semantics for WebSocket fan-out across backend instances."""

from __future__ import annotations

import asyncio
import json

import pytest

from src.core.redis import ISSUE_UPDATES_CHANNEL
from src.domains.notifications.api import routes


class FakeWebSocket:
    def __init__(self) -> None:
        self.sent: list[dict] = []

    async def send_json(self, data: dict) -> None:
        self.sent.append(data)


class FakePubSub:
    """Drain a fixed list, then cancel the listener cleanly."""

    def __init__(self, messages: list[dict]) -> None:
        self.messages = messages
        self.subscribed: list[str] = []
        self.closed = False

    async def subscribe(self, channel: str) -> None:
        self.subscribed.append(channel)

    async def get_message(self, *, ignore_subscribe_messages: bool, timeout: float) -> dict | None:
        if not self.messages:
            raise asyncio.CancelledError
        return self.messages.pop(0)

    async def close(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_broadcast_publishes_and_delivers_locally(monkeypatch):
    client = FakeWebSocket()
    monkeypatch.setattr(routes, "connected_clients", [client])

    published: list[tuple[str, dict]] = []

    async def fake_publish(channel: str, message: dict) -> bool:
        published.append((channel, message))
        return True

    monkeypatch.setattr(routes, "publish_message", fake_publish)

    await routes.broadcast_issue_update({"type": "issue_created", "payload": {"id": 7}})

    assert published[0][0] == ISSUE_UPDATES_CHANNEL
    assert published[0][1]["payload"] == {"type": "issue_created", "payload": {"id": 7}}
    # Local delivery is immediate, not dependent on the subscriber looping.
    assert client.sent == [{"type": "issue_created", "payload": {"id": 7}}]


@pytest.mark.asyncio
async def test_remote_event_reaches_local_client_but_own_echo_is_ignored(monkeypatch):
    client = FakeWebSocket()
    monkeypatch.setattr(routes, "connected_clients", [client])

    own = json.dumps({"instance": routes._INSTANCE_ID, "payload": {"type": "own"}})
    remote = json.dumps({"instance": "another-instance", "payload": {"type": "remote"}})
    pubsub = FakePubSub([{"data": own}, {"data": remote.encode("utf-8")}])

    with pytest.raises(asyncio.CancelledError):
        await routes._listen_for_updates(pubsub)

    assert client.sent == [{"type": "remote"}]
    assert pubsub.closed is True


@pytest.mark.asyncio
async def test_ensure_listener_subscribes_once_per_loop(monkeypatch):
    pubsub = FakePubSub([])
    monkeypatch.setattr(routes, "create_pubsub", lambda: pubsub)

    monkeypatch.setattr(routes, "_subscriber_task", None)
    monkeypatch.setattr(routes, "_subscriber_loop", None)

    await routes.ensure_issue_listener()
    first = routes._subscriber_task
    await routes.ensure_issue_listener()

    assert pubsub.subscribed == [ISSUE_UPDATES_CHANNEL]
    assert routes._subscriber_task is first

    if first is not None:
        first.cancel()
        with pytest.raises(asyncio.CancelledError):
            await first
