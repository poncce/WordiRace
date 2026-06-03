from fastapi import APIRouter, Depends, HTTPException, status

from app.core.dependencies import get_repo, get_room_manager
from app.core.exceptions import (
    RoomAlreadyStartedError, RoomFullError, RoomNotFoundError,
)
from app.repositories.redis_repository import RedisRepository
from app.schemas.messages import (
    CreateRoomRequest, CreateRoomResponse,
    HealthResponse, JoinRoomRequest, JoinRoomResponse,
)
from app.services.room_manager import RoomManager
from app.core.config import get_settings

settings = get_settings()
router = APIRouter()


@router.get("/health", response_model=HealthResponse, tags=["system"])
async def health(repo: RedisRepository = Depends(get_repo)):
    redis_ok = await repo.ping()
    return HealthResponse(
        status="ok",
        version=settings.APP_VERSION,
        redis=redis_ok,
    )


@router.post("/rooms", response_model=CreateRoomResponse, status_code=status.HTTP_201_CREATED, tags=["rooms"])
async def create_room(
    body: CreateRoomRequest,
    room_mgr: RoomManager = Depends(get_room_manager),
):
    """Create a new private room. Returns room code and player ID."""
    room, player = await room_mgr.create_room(
        nickname=body.nickname,
        word_length=body.word_length,
        max_attempts=body.max_attempts,
    )
    return CreateRoomResponse(room_code=room.code, player_id=player.id)


@router.post("/rooms/{room_code}/join", response_model=JoinRoomResponse, tags=["rooms"])
async def join_room(
    room_code: str,
    body: JoinRoomRequest,
    room_mgr: RoomManager = Depends(get_room_manager),
):
    """Join an existing room by code."""
    try:
        room, player = await room_mgr.join_room(room_code.upper(), body.nickname)
    except RoomNotFoundError:
        raise HTTPException(status_code=404, detail="Sala no encontrada")
    except RoomAlreadyStartedError:
        raise HTTPException(status_code=409, detail="La partida esta en progreso")
    except RoomFullError:
        raise HTTPException(status_code=409, detail="La sala está llena")
    return JoinRoomResponse(room_code=room.code, player_id=player.id)


@router.get("/rooms/{room_code}", tags=["rooms"])
async def get_room(
    room_code: str,
    repo: RedisRepository = Depends(get_repo),
):
    """Get current room state (for reconnection / polling)."""
    room = await repo.get_room(room_code.upper())
    if room is None:
        raise HTTPException(status_code=404, detail="Sala no encontrada")
    return {
        "code": room.code,
        "status": room.status.value,
        "players": len(room.players),
        "host_id": room.host_id,
        "settings": {
            "word_length": room.settings.word_length,
            "max_attempts": room.settings.max_attempts,
        },
    }
