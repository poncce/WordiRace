from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


def _find_env_file() -> str:
    """Find .env relative to this file, falling back to CWD."""
    here = Path(__file__).resolve().parent
    for candidate in (here / ".env", here.parent.parent.parent / ".env", Path(".env")):
        if candidate.exists():
            return str(candidate)
    return str(Path(".env"))


class Settings(BaseSettings):
    # App
    APP_NAME: str = "WordiRace"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False

    # Redis
    REDIS_URL: str = "redis://localhost:6379"
    REDIS_TTL_ROOM: int = 3600 * 6        # 6 horas
    REDIS_TTL_GAME: int = 3600 * 2        # 2 horas

    # RAE API
    RAE_API_BASE_URL: str = "https://rae-api.com/api"
    RAE_API_KEY: str = ""
    RAE_API_TIMEOUT: int = 5
    RAE_CACHE_TTL: int = 86400            # 24 horas

    # Game
    DEFAULT_WORD_LENGTH: int = 5
    DEFAULT_MAX_ATTEMPTS: int = 6
    MIN_WORD_LENGTH: int = 5
    MAX_WORD_LENGTH: int = 8
    MIN_PLAYERS: int = 1
    MAX_PLAYERS: int = 10

    # WebSocket
    WS_HEARTBEAT_INTERVAL: int = 30
    WS_MAX_MESSAGE_SIZE: int = 1024

    # Security
    RATE_LIMIT_GUESSES: int = 30          # por minuto
    ALLOWED_ORIGINS: list[str] = ["*"]

    model_config = SettingsConfigDict(
        env_file=_find_env_file(),
        env_file_encoding="utf-8",
    )


@lru_cache()
def get_settings() -> Settings:
    return Settings()
