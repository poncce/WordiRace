"""
GameManager
───────────
Owns all game logic:
  - Starting a game (word selection, countdown)
  - Processing guesses (Wordle evaluation algorithm)
  - Detecting win / end conditions
  - Building broadcast payloads
"""
from __future__ import annotations

import asyncio
import random
from datetime import datetime
from typing import Optional

from app.core.config import get_settings
from app.core.exceptions import (
    GameNotActiveError, InvalidWordLengthError, InvalidWordError,
    PlayerAlreadyFinishedError, RateLimitError,
)
from app.core.logging import get_logger
from app.models.domain import (
    Game, GameSettings, GameStatus, Guess, LetterFeedback, LetterResult, Player, Room,
)
from app.repositories.redis_repository import RedisRepository
from app.schemas.messages import (
    GuessSchema, LetterFeedbackSchema, OutboundMessage,
    PlayerSchema, WSEventType,
)
from app.services.word_validation_service import WordValidationService
from app.websocket.manager import WebSocketManager

log = get_logger(__name__)
settings = get_settings()

# Fallback word pool used ONLY when the RAE API is unavailable.
_WORD_POOL: dict[int, list[str]] = {
    5: ["PIANO", "BRUJA", "TIGRE", "FELIZ", "JUEGO", "PLAZA", "VIAJE", "DANZA",
        "FRESA", "HIELO", "LLAVE", "MUNDO", "NIEVE", "QUESO", "RIEGA", "SIETE",
        "TECHO", "VAPOR", "YERNO", "PLAYA", "GATOS", "LIBRO", "CASAS", "VIDAS"],
    6: ["FIESTA", "GRANJA", "CAMINO", "FRENOS", "BROCHA", "JARABE", "LADERA",
        "MUEBLE", "PISTOL", "RINCON", "DENTAL", "CABINA", "SALIDA", "NUBLAR"],
    7: ["ABOGADO", "BELLEZA", "CIGARRA", "DEFENSA", "ESPACIO", "FUNCION",
        "GANADOR", "HORMIGA", "IGLESIA", "JUGADOR", "MONTAÑA", "PELOTAS",
        "SOLDADO"],
    8: ["ARMADURA", "DIAMANTE", "ESCALERA", "BALCONES", "GUITARRA",
        "PARACAID", "CANDADOS", "MADRUGAR", "JUBILADO", "PRINCESA"],
}


def _pick_word_fallback(length: int) -> str:
    """Fallback: pick a word from the local pool when the API is unavailable."""
    pool = _WORD_POOL.get(length, _WORD_POOL[5])
    return random.choice(pool).upper()


def _evaluate_guess(guess: str, secret: str) -> list[LetterFeedback]:
    """
    Classic Wordle evaluation algorithm.
    Handles duplicate letters correctly.
    """
    result = [LetterResult.ABSENT] * len(guess)
    secret_remaining: list[Optional[str]] = list(secret)

    # Pass 1: mark correct positions (green)
    for i, (g, s) in enumerate(zip(guess, secret)):
        if g == s:
            result[i] = LetterResult.CORRECT
            secret_remaining[i] = None

    # Pass 2: mark present letters (yellow)
    for i, g in enumerate(guess):
        if result[i] == LetterResult.CORRECT:
            continue
        if g in secret_remaining:
            result[i] = LetterResult.PRESENT
            secret_remaining[secret_remaining.index(g)] = None

    return [LetterFeedback(letter=guess[i], result=result[i]) for i in range(len(guess))]


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


class GameManager:
    def __init__(
        self,
        repo: RedisRepository,
        ws_manager: WebSocketManager,
        word_validator: WordValidationService,
    ) -> None:
        self._repo = repo
        self._ws = ws_manager
        self._validator = word_validator

    # ── Game start ───────────────────────────────────────────────────────────

    async def start_game(self, room: Room) -> None:
        """Initialise game state and broadcast GAME_STARTING countdown.
        Resets all player states if a previous game had finished."""
        # Reset players from a previous finished game
        for p in room.players.values():
            p.guesses = []
            p.won = False
            p.finished = False
            p.finished_at = None
            p._rank = None
            await self._repo.save_player(p)

        # Fetch a random word from the RAE API; fallback to local pool if unavailable
        word = await self._validator.get_random_word(
            room.settings.word_length, room.settings.word_length
        )
        if word is None:
            word = _pick_word_fallback(room.settings.word_length)
            log.info("Using fallback pool for room %s (word=%s)", room.code, word)

        game = Game(
            room_code=room.code,
            secret_word=word,
            settings=room.settings,
        )
        room.game = game
        room.last_activity = datetime.utcnow()

        await self._repo.save_game(game)
        await self._repo.save_room(room)

        log.info("Game started in room %s | word=%s", room.code, word)

        # 3-second countdown
        await self._ws.broadcast(
            room.code,
            OutboundMessage(
                type=WSEventType.GAME_STARTING,
                payload={"countdown": 3, "word_length": room.settings.word_length,
                         "max_attempts": room.settings.max_attempts},
            ),
        )
        await asyncio.sleep(3)

        await self._ws.broadcast(
            room.code,
            OutboundMessage(
                type=WSEventType.GAME_STARTED,
                payload={
                    "word_length": room.settings.word_length,
                    "max_attempts": room.settings.max_attempts,
                    "started_at": game.started_at.isoformat(),
                },
            ),
        )

    # ── Guess processing ─────────────────────────────────────────────────────

    async def process_guess(
        self,
        room: Room,
        player: Player,
        raw_word: str,
    ) -> None:
        """Full guess pipeline: validate → evaluate → persist → broadcast."""
        game = room.game
        if game is None or game.status != GameStatus.PLAYING:
            raise GameNotActiveError()

        if player.finished:
            raise PlayerAlreadyFinishedError()

        # Rate limit
        if not await self._repo.check_rate_limit(player.id):
            raise RateLimitError()

        word = raw_word.upper()

        # Length check
        if len(word) != game.settings.word_length:
            raise InvalidWordLengthError(word, game.settings.word_length)

        # Word validity (RAE)
        if not await self._validator.is_valid(word):
            raise InvalidWordError(word)

        # Evaluate
        feedback = _evaluate_guess(word, game.secret_word)
        guess = Guess(word=word, feedback=feedback)
        player.guesses.append(guess)

        won = all(f.result == LetterResult.CORRECT for f in feedback)
        exhausted = player.attempts_used >= game.settings.max_attempts

        if won or exhausted:
            player.finished = True
            player.finished_at = datetime.utcnow()
            if won:
                player.won = True
                if game.winner_id is None:
                    game.winner_id = player.id
            game.finish_rank_counter += 1
            player.rank = game.finish_rank_counter

        await self._repo.save_player(player)

        # Send private result (includes word)
        await self._ws.send(
            player.id,
            OutboundMessage(
                type=WSEventType.GUESS_RESULT,
                payload={
                    "word": word,
                    "feedback": [
                        LetterFeedbackSchema(letter=f.letter, result=f.result.value)
                        for f in feedback
                    ],
                    "attempt": player.attempts_used,
                    "won": player.won,
                    "finished": player.finished,
                },
            ),
        )

        # Broadcast to others (no word revealed)
        await self._ws.broadcast(
            room.code,
            OutboundMessage(
                type=WSEventType.PLAYER_GUESS_MADE,
                payload={
                    "player_id": player.id,
                    "nickname": player.nickname,
                    "attempt": player.attempts_used,
                },
            ),
            exclude=player.id,
        )

        # Sync player back into room before end-check (player is a separate object)
        room.players[player.id] = player

        # Notify if player finished
        if player.finished:
            await self._ws.broadcast(
                room.code,
                OutboundMessage(
                    type=WSEventType.PLAYER_FINISHED,
                    payload=_player_schema(player).model_dump(),
                ),
            )

        # Check if game should end
        await self._check_game_end(room, game)

    async def _check_game_end(self, room: Room, game: Game) -> None:
        """End game if all connected players are finished."""
        active_players = [
            p for p in room.players.values() if p.connected
        ]
        all_done = all(p.finished for p in active_players)
        if not all_done:
            return

        game.status = GameStatus.FINISHED
        game.finished_at = datetime.utcnow()
        await self._repo.save_game(game)

        ranking = sorted(
            [p for p in active_players if p.rank is not None],
            key=lambda p: p.rank,
        )

        await self._ws.broadcast(
            room.code,
            OutboundMessage(
                type=WSEventType.GAME_FINISHED,
                payload={
                    "secret_word": game.secret_word,
                    "winner_id": game.winner_id,
                    "ranking": [_player_schema(p).model_dump() for p in ranking],
                    "finished_at": game.finished_at.isoformat(),
                },
            ),
        )
        log.info("Game finished in room %s | winner=%s", room.code, game.winner_id)
