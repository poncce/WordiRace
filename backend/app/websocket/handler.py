"""
WebSocket Handler
──────────────────
One coroutine per connection.
Dispatches inbound events to the appropriate service.
"""
from __future__ import annotations

import asyncio
import json

from fastapi import WebSocket, WebSocketDisconnect

from app.core.config import get_settings
from app.core.exceptions import WordleBaseError
from app.core.logging import get_logger
from app.models.domain import GameStatus
from app.repositories.redis_repository import RedisRepository
from app.schemas.messages import (
    InboundEventType, InboundMessage, OutboundMessage,
    SubmitGuessPayload, UpdateSettingsPayload, WSEventType,
)
from app.services.game_manager import GameManager
from app.services.room_manager import RoomManager
from app.websocket.manager import WebSocketManager

log = get_logger(__name__)
settings = get_settings()


class WebSocketHandler:
    def __init__(
        self,
        repo: RedisRepository,
        ws_manager: WebSocketManager,
        room_manager: RoomManager,
        game_manager: GameManager,
    ) -> None:
        self._repo = repo
        self._ws = ws_manager
        self._room_mgr = room_manager
        self._game_mgr = game_manager

    async def handle(
        self,
        websocket: WebSocket,
        room_code: str,
        player_id: str,
    ) -> None:
        """Main entry point: accept → setup → listen → cleanup."""
        await websocket.accept()

        # Load room & player from Redis
        room = await self._repo.get_room(room_code)
        player = await self._repo.get_player(player_id)

        if room is None or player is None:
            await websocket.close(code=4404, reason="Room or player not found")
            return

        # Register connection
        self._ws.register(player_id, room_code, websocket)

        # Handle reconnection
        if not player.connected:
            await self._room_mgr.reconnect_player(room, player)

        # Send current room state
        await self._ws.send(player_id, self._room_mgr.build_room_state(room))

        # Notify others
        await self._ws.broadcast(
            room_code,
            OutboundMessage(
                type=WSEventType.PLAYER_JOINED,
                payload={"player_id": player_id, "nickname": player.nickname},
            ),
            exclude=player_id,
        )

        # Start heartbeat task
        heartbeat_task = asyncio.create_task(
            self._heartbeat_loop(player_id)
        )

        try:
            async for raw in websocket.iter_text():
                await self._dispatch(raw, room_code, player_id)
        except WebSocketDisconnect:
            log.info("Player %s disconnected from room %s", player_id, room_code)
        except Exception as exc:
            log.error("Unexpected WS error for player %s: %s", player_id, exc)
        finally:
            heartbeat_task.cancel()
            # Reload fresh room from Redis before cleanup
            fresh_room = await self._repo.get_room(room_code)
            fresh_player = await self._repo.get_player(player_id)
            if fresh_room and fresh_player:
                await self._room_mgr.leave_room(fresh_room, fresh_player)
            self._ws.unregister(player_id, room_code, websocket)

    async def _dispatch(self, raw: str, room_code: str, player_id: str) -> None:
        """Parse and route inbound message."""
        # Size guard
        if len(raw) > settings.WS_MAX_MESSAGE_SIZE:
            await self._ws.broadcast_error(player_id, "Message too large")
            return

        try:
            data = json.loads(raw)
            msg = InboundMessage(**data)
        except Exception:
            await self._ws.broadcast_error(player_id, "Invalid message format")
            return

        # Reload state fresh from Redis on every message
        room = await self._repo.get_room(room_code)
        player = await self._repo.get_player(player_id)
        if room is None or player is None:
            return

        try:
            match msg.type:
                case InboundEventType.SUBMIT_GUESS:
                    payload = SubmitGuessPayload(**msg.payload)
                    await self._game_mgr.process_guess(room, player, payload.word)

                case InboundEventType.START_GAME:
                    if not player.is_host:
                        await self._ws.broadcast_error(player_id, "Only the host can start the game")
                        return
                    if room.status == GameStatus.PLAYING:
                        await self._ws.broadcast_error(player_id, "Game already in progress")
                        return
                    await self._game_mgr.start_game(room)

                case InboundEventType.UPDATE_SETTINGS:
                    payload = UpdateSettingsPayload(**msg.payload)
                    await self._room_mgr.update_settings(
                        room, player,
                        payload.word_length,
                        payload.max_attempts,
                    )

                case InboundEventType.LEAVE_ROOM:
                    await self._room_mgr.leave_room(room, player)
                    self._ws.unregister(player_id, room_code)

                case InboundEventType.PING:
                    await self._ws.send(
                        player_id,
                        OutboundMessage(type=WSEventType.HEARTBEAT, payload={"pong": True}),
                    )

        except WordleBaseError as exc:
            await self._ws.broadcast_error(player_id, str(exc))
        except Exception as exc:
            log.error("Error dispatching %s for player %s: %s", msg.type, player_id, exc)
            await self._ws.broadcast_error(player_id, "Internal server error")

    async def _heartbeat_loop(self, player_id: str) -> None:
        """Send periodic heartbeats to keep connection alive."""
        try:
            while True:
                await asyncio.sleep(settings.WS_HEARTBEAT_INTERVAL)
                ok = await self._ws.send_heartbeat(player_id)
                if not ok:
                    break
        except asyncio.CancelledError:
            pass
