"""
Dependencies
────────────
FastAPI dependency-injection wiring.
All services are singletons shared across requests.
"""
from __future__ import annotations

import redis.asyncio as aioredis

from app.core.config import get_settings
from app.repositories.redis_repository import RedisRepository
from app.services.game_manager import GameManager
from app.services.room_manager import RoomManager
from app.services.word_validation_service import WordValidationService
from app.websocket.handler import WebSocketHandler
from app.websocket.manager import WebSocketManager

settings = get_settings()

# ── Singletons ────────────────────────────────────────────────────────────────

_redis_client: aioredis.Redis | None = None
_repo: RedisRepository | None = None
_ws_manager: WebSocketManager | None = None
_word_validator: WordValidationService | None = None
_room_manager: RoomManager | None = None
_game_manager: GameManager | None = None
_ws_handler: WebSocketHandler | None = None


async def init_dependencies() -> None:
    global _redis_client, _repo, _ws_manager, _word_validator
    global _room_manager, _game_manager, _ws_handler

    _redis_client = aioredis.from_url(
        settings.REDIS_URL,
        encoding="utf-8",
        decode_responses=False,
        protocol=2,  # RESP2 for Redis 3.0 on Windows
    )
    _repo = RedisRepository(_redis_client)
    _ws_manager = WebSocketManager()
    _word_validator = WordValidationService(_repo)
    _room_manager = RoomManager(_repo, _ws_manager)
    _game_manager = GameManager(_repo, _ws_manager, _word_validator)
    _ws_handler = WebSocketHandler(_repo, _ws_manager, _room_manager, _game_manager)


async def close_dependencies() -> None:
    if _word_validator:
        await _word_validator.close()
    if _redis_client:
        await _redis_client.aclose()


# ── FastAPI dependencies ──────────────────────────────────────────────────────

def get_repo() -> RedisRepository:
    assert _repo is not None
    return _repo


def get_ws_manager() -> WebSocketManager:
    assert _ws_manager is not None
    return _ws_manager


def get_room_manager() -> RoomManager:
    assert _room_manager is not None
    return _room_manager


def get_game_manager() -> GameManager:
    assert _game_manager is not None
    return _game_manager


def get_ws_handler() -> WebSocketHandler:
    assert _ws_handler is not None
    return _ws_handler
