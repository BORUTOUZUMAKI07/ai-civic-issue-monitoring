"""WebSocket fan-out that works across multiple backend instances.

Each process keeps only its own connected sockets. Every event is published to
Redis once and delivered to those local sockets immediately; a per-process
subscriber replays events published by *other* instances. Messages carry the
publisher's instance id so its own subscriber can ignore the echo — no client
receives the same event twice.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.core.redis import ISSUE_UPDATES_CHANNEL, create_pubsub, publish_message

router = APIRouter(tags=["WebSocket"])

logger = logging.getLogger("civicpulse")

connected_clients: list[WebSocket] = []

_INSTANCE_ID = uuid.uuid4().hex
_subscriber_task: asyncio.Task[None] | None = None
_subscriber_loop: asyncio.AbstractEventLoop | None = None


async def _send_to_local_clients(data: dict[str, Any]) -> None:
    """Best-effort delivery to sockets attached to *this* instance."""
    disconnected: list[WebSocket] = []
    for client in list(connected_clients):
        try:
            await client.send_json(data)
        except Exception:
            disconnected.append(client)
    for client in disconnected:
        try:
            connected_clients.remove(client)
        except ValueError:
            pass


async def _listen_for_updates(pubsub: Any) -> None:
    """Forward messages from other instances to this instance's clients."""
    try:
        while True:
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if not message:
                continue
            raw = message.get("data")
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8")
            if not isinstance(raw, str):
                continue
            try:
                envelope = json.loads(raw)
            except (TypeError, ValueError):
                logger.warning("Ignoring malformed WebSocket pub/sub message.")
                continue
            # Our own event was already delivered by broadcast_issue_update.
            if envelope.get("instance") == _INSTANCE_ID:
                continue
            payload = envelope.get("payload")
            if isinstance(payload, dict):
                await _send_to_local_clients(payload)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.warning("WebSocket Redis listener stopped: %s", exc)
    finally:
        try:
            await pubsub.close()
        except Exception:  # nosec B110 - shutdown is best-effort
            pass


async def ensure_issue_listener() -> None:
    """Start one subscriber per process/event loop, on first WS connection.

    Starting lazily avoids touching Redis during app startup and keeps tests
    (which build the app without a lifespan) fully in-process. The loop guard
    replaces a stale task if a new event loop is created, e.g. across tests.
    """
    global _subscriber_task, _subscriber_loop

    loop = asyncio.get_running_loop()
    if _subscriber_task is not None and not _subscriber_task.done() and _subscriber_loop is loop:
        return
    if _subscriber_task is not None and not _subscriber_task.done():
        _subscriber_task.cancel()

    pubsub = create_pubsub()
    if pubsub is None:
        return
    try:
        await pubsub.subscribe(ISSUE_UPDATES_CHANNEL)
    except Exception as exc:
        logger.warning("WebSocket subscribe failed: %s", exc)
        return

    _subscriber_loop = loop
    _subscriber_task = asyncio.create_task(_listen_for_updates(pubsub))


async def authenticate_ws_token(token: str, db: AsyncSession) -> int | None:
    """Validate a WebSocket credential and return its live user id.

    Kept separate from the socket handler so the trust boundary is testable
    without a live connection. ``None`` means "close the socket"; the handler
    never learns anything else about the caller.
    """
    from src.core.security import decode_token, is_token_blacklisted
    from src.domains.users.repositories.user_repository import UserRepository

    try:
        payload = decode_token(token)
        # ``access`` is accepted so an existing cookie/header token keeps
        # working (tests, CLI); browsers use the short-lived ``ws`` ticket
        # minted by ``GET /auth/ws-ticket`` because the HttpOnly access cookie
        # is unreadable from JavaScript. Every other token purpose (refresh,
        # password reset, 2FA challenge) is rejected here.
        if payload.get("type") not in ("access", "ws"):
            return None
        user_id = int(payload["sub"])
        if payload.get("jti") and await is_token_blacklisted(payload["jti"]):
            return None
        # A ticket for a deleted or deactivated account must not keep streaming
        # issue updates after the account is closed.
        user = await UserRepository(db).get(user_id)
        if user is None or not user.is_active:
            return None
        return user_id
    except Exception:
        return None


@router.websocket("/ws/issues")
async def websocket_issues(
    websocket: WebSocket,
    token: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    if await authenticate_ws_token(token, db) is None:
        await websocket.close(code=4001, reason="Invalid token")
        return

    await ensure_issue_listener()
    await websocket.accept()
    connected_clients.append(websocket)
    logger.info("WebSocket client connected. Total: %d", len(connected_clients))
    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        try:
            connected_clients.remove(websocket)
        except ValueError:
            pass
        logger.info("WebSocket client disconnected. Total: %d", len(connected_clients))


async def broadcast_issue_update(data: dict[str, Any]) -> None:
    """Publish once for every instance, and deliver locally without waiting.

    The local send is unconditional so a Redis outage cannot break real-time
    updates on the instance that handled the request. Remote instances receive
    the event through their subscriber and ignore messages they published
    themselves (matched by ``_INSTANCE_ID``).
    """
    await publish_message(
        ISSUE_UPDATES_CHANNEL,
        {"instance": _INSTANCE_ID, "payload": data},
    )
    await _send_to_local_clients(data)
