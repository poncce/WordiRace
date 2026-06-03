from fastapi import APIRouter, Depends, WebSocket

from app.core.dependencies import get_ws_handler
from app.websocket.handler import WebSocketHandler

router = APIRouter()


@router.websocket("/ws/{room_code}/{player_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    room_code: str,
    player_id: str,
    handler: WebSocketHandler = Depends(get_ws_handler),
):
    """
    WebSocket connection endpoint.
    URL: ws://host/ws/{ROOM_CODE}/{PLAYER_ID}
    """
    await handler.handle(websocket, room_code.upper(), player_id)
