import logging

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

router = APIRouter(tags=["WebSocket"])

logger = logging.getLogger("civicpulse")

connected_clients: list[WebSocket] = []


@router.websocket("/ws/issues")
async def websocket_issues(websocket: WebSocket, token: str = Query(...)):
    from src.core.security import decode_token

    try:
        payload = decode_token(token)
        if payload.get("type") != "access":
            await websocket.close(code=4001, reason="Invalid token type")
            return
    except Exception:
        await websocket.close(code=4001, reason="Invalid token")
        return

    await websocket.accept()
    connected_clients.append(websocket)
    logger.info("WebSocket client connected. Total: %d", len(connected_clients))
    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        connected_clients.remove(websocket)
        logger.info("WebSocket client disconnected. Total: %d", len(connected_clients))


async def broadcast_issue_update(data: dict):
    disconnected = []
    for client in connected_clients:
        try:
            await client.send_json(data)
        except Exception:
            disconnected.append(client)
    for client in disconnected:
        connected_clients.remove(client)
