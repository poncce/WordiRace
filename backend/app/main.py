from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse

from app.api.routes import rooms as rooms_router
from app.api.routes import websocket as ws_router
from app.core.config import get_settings
from app.core.dependencies import close_dependencies, init_dependencies
from app.core.logging import setup_logging

settings = get_settings()
setup_logging()

FRONTEND_DIR = Path(__file__).resolve().parent.parent.parent / "frontend"


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_dependencies()
    yield
    await close_dependencies()


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    lifespan=lifespan,
    docs_url="/api/docs" if settings.DEBUG else None,
    redoc_url=None,
)


@app.exception_handler(Exception)
async def catch_all_exceptions(request: Request, exc: Exception):
    import traceback
    tb = traceback.format_exception(type(exc), exc, exc.__traceback__)
    print("".join(tb))
    return JSONResponse(
        status_code=500,
        content={"detail": str(exc), "traceback": "".join(tb)},
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# REST routes
app.include_router(rooms_router.router, prefix="/api")

# WebSocket routes
app.include_router(ws_router.router)

# Serve frontend static files
app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
