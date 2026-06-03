"""
WebSocketManager
─────────────────
Manages all active WebSocket connections, keyed by player_id.
Provides targeted send (to one player) and broadcast (to a room).
Handles disconnections gracefully.
"""
from __future__ import annotations

import asyncio
from typing import Optional

from fastapi import WebSocket

from app.core.logging import get_logger
from app.schemas.messages import OutboundMessage, WSEventType

log = get_logger(__name__)


class WebSocketManager:
    def __init__(self) -> None:
        # player_id → WebSocket
        self._connections: dict[str, WebSocket] = {}
        # room_code → set of player_ids
        self._room_members: dict[str, set[str]] = {}

    # ── Connection lifecycle ─────────────────────────────────────────────────

    def register(self, player_id: str, room_code: str, ws: WebSocket) -> None:
        self._connections[player_id] = ws
        self._room_members.setdefault(room_code, set()).add(player_id)
        log.info("WS registered: player=%s room=%s", player_id, room_code)

    def unregister(self, player_id: str, room_code: str, ws: WebSocket | None = None) -> None:
        # Only remove from _connections if the ws matches (avoids race when a new
        # connection is registered before the old handler's cleanup runs).
        if ws is None or self._connections.get(player_id) is ws:
            self._connections.pop(player_id, None)
        if room_code in self._room_members:
            self._room_members[room_code].discard(player_id)
            if not self._room_members[room_code]:
                del self._room_members[room_code]
        log.info("WS unregistered: player=%s room=%s", player_id, room_code)

    def is_connected(self, player_id: str) -> bool:
        return player_id in self._connections

    # ── Messaging ────────────────────────────────────────────────────────────

    async def send(self, player_id: str, message: OutboundMessage) -> bool:
        """Send message to a single player. Returns False if not connected."""
        ws = self._connections.get(player_id)
        if ws is None:
            return False
        try:
            await ws.send_text(message.to_json())
            return True
        except Exception as exc:
            log.warning("Failed to send to player %s: %s", player_id, exc)
            return False

    async def broadcast(
        self,
        room_code: str,
        message: OutboundMessage,
        exclude: Optional[str] = None,
    ) -> None:
        """Broadcast message to all players in a room."""
        members = self._room_members.get(room_code, set()).copy()
        tasks = [
            self.send(pid, message)
            for pid in members
            if pid != exclude
        ]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def broadcast_error(self, player_id: str, detail: str) -> None:
        msg = OutboundMessage(
            type=WSEventType.ERROR,
            payload={"detail": detail},
        )
        await self.send(player_id, msg)

    # ── Heartbeat ────────────────────────────────────────────────────────────

    async def send_heartbeat(self, player_id: str) -> bool:
        msg = OutboundMessage(type=WSEventType.HEARTBEAT, payload={})
        return await self.send(player_id, msg)

    # ── Stats ─────────────────────────────────────────────────────────────────

    @property
    def total_connections(self) -> int:
        return len(self._connections)

    def room_connection_count(self, room_code: str) -> int:
        return len(self._room_members.get(room_code, set()))
