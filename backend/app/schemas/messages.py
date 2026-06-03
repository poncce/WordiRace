from __future__ import annotations
from datetime import datetime
from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field, field_validator


# ──────────────────────────────────────────
# WebSocket event types
# ──────────────────────────────────────────

class WSEventType(str, Enum):
    # Connection lifecycle
    CONNECTED       = "connected"
    PLAYER_JOINED   = "player_joined"
    PLAYER_LEFT     = "player_left"
    PLAYER_RECONNECTED = "player_reconnected"

    # Room
    ROOM_STATE      = "room_state"
    ROOM_SETTINGS_UPDATED = "room_settings_updated"
    HOST_CHANGED    = "host_changed"

    # Game lifecycle
    GAME_STARTING   = "game_starting"       # countdown begins
    GAME_STARTED    = "game_started"
    GAME_FINISHED   = "game_finished"

    # Gameplay
    GUESS_RESULT    = "guess_result"        # your own guess result
    PLAYER_GUESS_MADE = "player_guess_made" # other player made a guess (no word revealed)
    PLAYER_FINISHED = "player_finished"     # a player won or exhausted attempts

    # System
    HEARTBEAT       = "heartbeat"
    ERROR           = "error"


# ──────────────────────────────────────────
# Inbound messages (client → server)
# ──────────────────────────────────────────

class InboundEventType(str, Enum):
    SUBMIT_GUESS    = "submit_guess"
    PING            = "ping"
    UPDATE_SETTINGS = "update_settings"     # host only
    START_GAME      = "start_game"          # host only
    LEAVE_ROOM      = "leave_room"


class InboundMessage(BaseModel):
    type: InboundEventType
    payload: dict[str, Any] = Field(default_factory=dict)


class SubmitGuessPayload(BaseModel):
    word: str

    @field_validator("word")
    @classmethod
    def normalize(cls, v: str) -> str:
        return v.strip().upper()


class UpdateSettingsPayload(BaseModel):
    word_length: Optional[int] = Field(None, ge=5, le=8)
    max_attempts: Optional[int] = Field(None, ge=3, le=10)


# ──────────────────────────────────────────
# Outbound schemas (server → client)
# ──────────────────────────────────────────

class LetterFeedbackSchema(BaseModel):
    letter: str
    result: str                             # "correct" | "present" | "absent"


class GuessSchema(BaseModel):
    word: str
    feedback: list[LetterFeedbackSchema]
    submitted_at: datetime


class PlayerSchema(BaseModel):
    id: str
    nickname: str
    is_host: bool
    guesses_count: int
    won: bool
    finished: bool
    connected: bool
    rank: Optional[int]


class GameSchema(BaseModel):
    status: str
    word_length: int
    max_attempts: int
    started_at: Optional[datetime]
    winner_id: Optional[str]


class RoomStateSchema(BaseModel):
    code: str
    host_id: str
    status: str
    settings: dict
    players: list[PlayerSchema]
    game: Optional[GameSchema]


class OutboundMessage(BaseModel):
    type: WSEventType
    payload: Any = None

    def to_json(self) -> str:
        return self.model_dump_json()


# ──────────────────────────────────────────
# REST API schemas
# ──────────────────────────────────────────

class CreateRoomRequest(BaseModel):
    nickname: str = Field(..., min_length=2, max_length=20)
    word_length: int = Field(5, ge=5, le=8)
    max_attempts: int = Field(6, ge=3, le=10)

    @field_validator("nickname")
    @classmethod
    def sanitize(cls, v: str) -> str:
        return v.strip()


class JoinRoomRequest(BaseModel):
    nickname: str = Field(..., min_length=2, max_length=20)

    @field_validator("nickname")
    @classmethod
    def sanitize(cls, v: str) -> str:
        return v.strip()


class CreateRoomResponse(BaseModel):
    room_code: str
    player_id: str


class JoinRoomResponse(BaseModel):
    room_code: str
    player_id: str


class HealthResponse(BaseModel):
    status: str
    version: str
    redis: bool
