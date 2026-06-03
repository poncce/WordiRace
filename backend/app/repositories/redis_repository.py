"""
RedisRepository
───────────────
All Redis I/O lives here.  Services never touch Redis directly.

Key schema:
  room:{code}           → JSON of Room (without WebSocket handles)
  game:{code}           → JSON of Game
  player:{id}           → JSON of Player
  room_players:{code}   → SET of player_ids
  word_cache:{word}     → "1" (word exists) | "0" (word invalid)
  rate:{player_id}      → counter (guesses per minute)
"""
from __future__ import annotations
import json
from datetime import datetime
from typing import Optional

import redis.asyncio as aioredis

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.domain import (
    Game, GameSettings, GameStatus, Guess, LetterFeedback,
    LetterResult, Player, Room,
)

log = get_logger(__name__)
settings = get_settings()

# ── serialisation helpers ──────────────────────────────────────────────────────

def _serialize_feedback(fb: list[LetterFeedback]) -> list[dict]:
    return [{"letter": f.letter, "result": f.result.value} for f in fb]


def _deserialize_feedback(data: list[dict]) -> list[LetterFeedback]:
    return [LetterFeedback(d["letter"], LetterResult(d["result"])) for d in data]


def _serialize_guess(g: Guess) -> dict:
    return {
        "word": g.word,
        "feedback": _serialize_feedback(g.feedback),
        "submitted_at": g.submitted_at.isoformat(),
    }


def _deserialize_guess(d: dict) -> Guess:
    return Guess(
        word=d["word"],
        feedback=_deserialize_feedback(d["feedback"]),
        submitted_at=datetime.fromisoformat(d["submitted_at"]),
    )


def _serialize_player(p: Player) -> dict:
    return {
        "id": p.id,
        "nickname": p.nickname,
        "room_code": p.room_code,
        "is_host": p.is_host,
        "guesses": [_serialize_guess(g) for g in p.guesses],
        "won": p.won,
        "finished": p.finished,
        "connected": p.connected,
        "joined_at": p.joined_at.isoformat(),
        "finished_at": p.finished_at.isoformat() if p.finished_at else None,
        "_rank": getattr(p, "_rank", None),
    }


def _deserialize_player(d: dict) -> Player:
    p = Player(
        id=d["id"],
        nickname=d["nickname"],
        room_code=d["room_code"],
        is_host=d["is_host"],
        guesses=[_deserialize_guess(g) for g in d.get("guesses", [])],
        won=d["won"],
        finished=d["finished"],
        connected=d["connected"],
        joined_at=datetime.fromisoformat(d["joined_at"]),
        finished_at=datetime.fromisoformat(d["finished_at"]) if d["finished_at"] else None,
    )
    if d.get("_rank") is not None:
        p.rank = d["_rank"]
    return p


def _serialize_game(g: Game) -> dict:
    return {
        "room_code": g.room_code,
        "secret_word": g.secret_word,
        "settings": {
            "word_length": g.settings.word_length,
            "max_attempts": g.settings.max_attempts,
        },
        "status": g.status.value,
        "started_at": g.started_at.isoformat(),
        "finished_at": g.finished_at.isoformat() if g.finished_at else None,
        "winner_id": g.winner_id,
        "finish_rank_counter": g.finish_rank_counter,
    }


def _deserialize_game(d: dict) -> Game:
    return Game(
        room_code=d["room_code"],
        secret_word=d["secret_word"],
        settings=GameSettings(**d["settings"]),
        status=GameStatus(d["status"]),
        started_at=datetime.fromisoformat(d["started_at"]),
        finished_at=datetime.fromisoformat(d["finished_at"]) if d["finished_at"] else None,
        winner_id=d["winner_id"],
        finish_rank_counter=d["finish_rank_counter"],
    )


def _serialize_room(r: Room) -> dict:
    return {
        "code": r.code,
        "host_id": r.host_id,
        "settings": {
            "word_length": r.settings.word_length,
            "max_attempts": r.settings.max_attempts,
        },
        "created_at": r.created_at.isoformat(),
        "last_activity": r.last_activity.isoformat(),
    }


def _deserialize_room(d: dict) -> Room:
    return Room(
        code=d["code"],
        host_id=d["host_id"],
        settings=GameSettings(**d["settings"]),
        created_at=datetime.fromisoformat(d["created_at"]),
        last_activity=datetime.fromisoformat(d["last_activity"]),
    )


# ── repository ─────────────────────────────────────────────────────────────────

class RedisRepository:
    def __init__(self, redis: aioredis.Redis):
        self._r = redis

    # ── Room ────────────────────────────────────────────────────────────────

    async def save_room(self, room: Room) -> None:
        key = f"room:{room.code}"
        await self._r.setex(key, settings.REDIS_TTL_ROOM, json.dumps(_serialize_room(room)))

    async def get_room(self, code: str) -> Optional[Room]:
        raw = await self._r.get(f"room:{code}")
        if not raw:
            return None
        room = _deserialize_room(json.loads(raw))
        # Reattach players
        player_ids = await self._r.smembers(f"room_players:{code}")
        for pid in player_ids:
            player = await self.get_player(pid.decode())
            if player:
                room.players[player.id] = player
        # Reattach game
        room.game = await self.get_game(code)
        return room

    async def delete_room(self, code: str) -> None:
        async with self._r.pipeline(transaction=True) as pipe:
            pipe.delete(f"room:{code}")
            pipe.delete(f"room_players:{code}")
            pipe.delete(f"game:{code}")
            await pipe.execute()
        log.info("Room %s deleted from Redis", code)

    async def touch_room(self, code: str) -> None:
        await self._r.expire(f"room:{code}", settings.REDIS_TTL_ROOM)

    # ── Player ──────────────────────────────────────────────────────────────

    async def save_player(self, player: Player) -> None:
        key = f"player:{player.id}"
        await self._r.setex(key, settings.REDIS_TTL_ROOM, json.dumps(_serialize_player(player)))
        await self._r.sadd(f"room_players:{player.room_code}", player.id)

    async def get_player(self, player_id: str) -> Optional[Player]:
        raw = await self._r.get(f"player:{player_id}")
        if not raw:
            return None
        return _deserialize_player(json.loads(raw))

    async def delete_player(self, player: Player) -> None:
        await self._r.delete(f"player:{player.id}")
        await self._r.srem(f"room_players:{player.room_code}", player.id)

    # ── Game ────────────────────────────────────────────────────────────────

    async def save_game(self, game: Game) -> None:
        key = f"game:{game.room_code}"
        await self._r.setex(key, settings.REDIS_TTL_GAME, json.dumps(_serialize_game(game)))

    async def get_game(self, room_code: str) -> Optional[Game]:
        raw = await self._r.get(f"game:{room_code}")
        if not raw:
            return None
        return _deserialize_game(json.loads(raw))

    async def delete_game(self, room_code: str) -> None:
        await self._r.delete(f"game:{room_code}")

    # ── Word cache ──────────────────────────────────────────────────────────

    async def get_word_cache(self, word: str) -> Optional[bool]:
        raw = await self._r.get(f"word_cache:{word}")
        if raw is None:
            return None
        return raw.decode() == "1"

    async def set_word_cache(self, word: str, valid: bool) -> None:
        await self._r.setex(f"word_cache:{word}", settings.RAE_CACHE_TTL, "1" if valid else "0")

    # ── Rate limiting ────────────────────────────────────────────────────────

    async def check_rate_limit(self, player_id: str) -> bool:
        """Returns True if the player is within the allowed rate."""
        key = f"rate:{player_id}"
        count = await self._r.incr(key)
        if count == 1:
            await self._r.expire(key, 60)
        return count <= settings.RATE_LIMIT_GUESSES

    # ── Health ───────────────────────────────────────────────────────────────

    async def ping(self) -> bool:
        try:
            return await self._r.ping()
        except Exception:
            return False
