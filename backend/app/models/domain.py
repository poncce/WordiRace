from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class GameStatus(str, Enum):
    WAITING = "waiting"
    PLAYING = "playing"
    FINISHED = "finished"


class LetterResult(str, Enum):
    CORRECT = "correct"       # Verde  — letra en posición exacta
    PRESENT = "present"       # Amarillo — letra existe pero en otro lugar
    ABSENT = "absent"         # Gris   — letra no existe en la palabra


@dataclass
class LetterFeedback:
    letter: str
    result: LetterResult


@dataclass
class Guess:
    word: str
    feedback: list[LetterFeedback]
    submitted_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class Player:
    id: str                                   # UUID
    nickname: str
    room_code: str
    is_host: bool = False
    guesses: list[Guess] = field(default_factory=list)
    won: bool = False
    finished: bool = False                    # won OR exhausted attempts
    connected: bool = True
    joined_at: datetime = field(default_factory=datetime.utcnow)
    finished_at: Optional[datetime] = None

    @property
    def attempts_used(self) -> int:
        return len(self.guesses)

    @property
    def rank(self) -> Optional[int]:
        """Set externally by GameManager when player finishes."""
        return getattr(self, "_rank", None)

    @rank.setter
    def rank(self, value: int) -> None:
        self._rank = value


@dataclass
class GameSettings:
    word_length: int = 5
    max_attempts: int = 6


@dataclass
class Game:
    room_code: str
    secret_word: str
    settings: GameSettings
    status: GameStatus = GameStatus.PLAYING
    started_at: datetime = field(default_factory=datetime.utcnow)
    finished_at: Optional[datetime] = None
    winner_id: Optional[str] = None
    finish_rank_counter: int = 0            # tracks order of finishes


@dataclass
class Room:
    code: str
    host_id: str
    settings: GameSettings
    players: dict[str, Player] = field(default_factory=dict)
    game: Optional[Game] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_activity: datetime = field(default_factory=datetime.utcnow)

    @property
    def status(self) -> GameStatus:
        if self.game is None:
            return GameStatus.WAITING
        return self.game.status

    @property
    def is_full(self) -> bool:
        from app.core.config import get_settings
        return len(self.players) >= get_settings().MAX_PLAYERS

    @property
    def connected_players(self) -> list[Player]:
        return [p for p in self.players.values() if p.connected]
