"""
RoomManager
───────────
Handles room and player lifecycle:
  - create / join / leave rooms
  - host management
  - player reconnection
  - room cleanup
"""
from __future__ import annotations

import secrets
import uuid
from datetime import datetime

from app.core.config import get_settings
from app.core.exceptions import (
    PlayerNotHostError, RoomAlreadyStartedError,
    RoomFullError, RoomNotFoundError,
)
from app.core.logging import get_logger
from app.models.domain import GameSettings, GameStatus, Player, Room
from app.repositories.redis_repository import RedisRepository
from app.schemas.messages import (
    OutboundMessage, PlayerSchema, RoomStateSchema, WSEventType,
)
from app.websocket.manager import WebSocketManager

log = get_logger(__name__)
settings = get_settings()


def _room_code() -> str:
    return secrets.token_hex(3).upper()       # 6-char hex, e.g. "A3F91C"


def _player_schema(p: Player) -> PlayerSchema:
    return PlayerSchema(
        id=p.id,
        nickname=p.nickname,
        is_host=p.is_host,
        guesses_count=p.attempts_used,
        won=p.won,
        finished=p.finished,
        connected=p.connected,
        rank=p.rank,
    )


def _room_state_payload(room: Room) -> dict:
    game = room.game
    return RoomStateSchema(
        code=room.code,
        host_id=room.host_id,
        status=room.status.value,
        settings={
            "word_length": room.settings.word_length,
            "max_attempts": room.settings.max_attempts,
        },
        players=[_player_schema(p) for p in room.players.values()],
        game=None if game is None else {
            "status": game.status.value,
            "word_length": game.settings.word_length,
            "max_attempts": game.settings.max_attempts,
            "started_at": game.started_at.isoformat() if game.started_at else None,
            "winner_id": game.winner_id,
        },
    ).model_dump()


class RoomManager:
    def __init__(self, repo: RedisRepository, ws_manager: WebSocketManager) -> None:
        self._repo = repo
        self._ws = ws_manager

    # ── Create ───────────────────────────────────────────────────────────────

    async def create_room(
        self,
        nickname: str,
        word_length: int,
        max_attempts: int,
    ) -> tuple[Room, Player]:
        code = _room_code()
        player_id = str(uuid.uuid4())

        game_settings = GameSettings(word_length=word_length, max_attempts=max_attempts)
        player = Player(id=player_id, nickname=nickname, room_code=code, is_host=True)
        room = Room(code=code, host_id=player_id, settings=game_settings)
        room.players[player_id] = player

        await self._repo.save_player(player)
        await self._repo.save_room(room)
        log.info("Room %s created by %s (%s)", code, nickname, player_id)
        return room, player

    # ── Join ─────────────────────────────────────────────────────────────────

    async def join_room(self, code: str, nickname: str) -> tuple[Room, Player]:
        room = await self._repo.get_room(code)
        if room is None:
            raise RoomNotFoundError(code)
        if room.status == GameStatus.PLAYING:
            raise RoomAlreadyStartedError(code)
        if room.is_full:
            raise RoomFullError(code)

        player_id = str(uuid.uuid4())
        player = Player(id=player_id, nickname=nickname, room_code=code)
        room.players[player_id] = player
        room.last_activity = datetime.utcnow()

        await self._repo.save_player(player)
        await self._repo.save_room(room)

        log.info("Player %s (%s) joined room %s", nickname, player_id, code)
        return room, player

    # ── Leave ────────────────────────────────────────────────────────────────

    async def leave_room(self, room: Room, player: Player) -> None:
        player.connected = False
        await self._repo.save_player(player)

        # Broadcast departure (exclude the departing player)
        await self._ws.broadcast(
            room.code,
            OutboundMessage(
                type=WSEventType.PLAYER_LEFT,
                payload={"player_id": player.id, "nickname": player.nickname},
            ),
            exclude=player.id,
        )

        # Check if room is now empty
        connected = room.connected_players
        connected = [p for p in connected if p.id != player.id]
        if not connected:
            if room.game is None:
                await self._repo.delete_room(room.code)
                log.info("Room %s cleaned up (empty)", room.code)
            return

        # Transfer host if needed
        if player.is_host:
            new_host = connected[0]
            new_host.is_host = True
            room.host_id = new_host.id
            await self._repo.save_player(new_host)
            await self._repo.save_room(room)
            await self._ws.broadcast(
                room.code,
                OutboundMessage(
                    type=WSEventType.HOST_CHANGED,
                    payload={"new_host_id": new_host.id, "nickname": new_host.nickname},
                ),
            )
            log.info("Host transferred to %s in room %s", new_host.nickname, room.code)

        # Caller (handler) is responsible for _ws.unregister()

    # ── Reconnect ────────────────────────────────────────────────────────────

    async def reconnect_player(self, room: Room, player: Player) -> None:
        player.connected = True
        await self._repo.save_player(player)
        await self._ws.broadcast(
            room.code,
            OutboundMessage(
                type=WSEventType.PLAYER_RECONNECTED,
                payload={"player_id": player.id, "nickname": player.nickname},
            ),
        )

    # ── Settings ──────────────────────────────────────────────────────────────

    async def update_settings(
        self,
        room: Room,
        player: Player,
        word_length: int | None,
        max_attempts: int | None,
    ) -> None:
        if not player.is_host:
            raise PlayerNotHostError()
        if word_length is not None:
            room.settings.word_length = word_length
        if max_attempts is not None:
            room.settings.max_attempts = max_attempts
        await self._repo.save_room(room)
        await self._ws.broadcast(
            room.code,
            OutboundMessage(
                type=WSEventType.ROOM_SETTINGS_UPDATED,
                payload={
                    "word_length": room.settings.word_length,
                    "max_attempts": room.settings.max_attempts,
                },
            ),
        )

    # ── State snapshot ────────────────────────────────────────────────────────

    def build_room_state(self, room: Room) -> OutboundMessage:
        return OutboundMessage(
            type=WSEventType.ROOM_STATE,
            payload=_room_state_payload(room),
        )
