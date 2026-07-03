"""MentorMan Unified Backend — FastAPI application entry point."""

import asyncio
import logging
import logging.handlers
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config.database import connect_db, disconnect_db
from app.config.settings import get_settings
from app.auth.admin_router import router as admin_router
from app.auth.router import router as auth_router
from app.routers import (
    ingest,
    memory,
    mentor,
    onboarding,
    profile,
    session_upload,
    sessions,
    skills,
    topics,
)
from app.services.session_manager import SessionManager


def _configure_logging() -> None:
    settings = get_settings()
    level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)

    logs_dir = Path(__file__).resolve().parents[1] / "logs"
    logs_dir.mkdir(exist_ok=True)

    fmt = logging.Formatter("%(asctime)s | %(levelname)-8s | %(name)s | %(message)s")

    # Rotate at midnight, keep 30 days, suffix = YYYY-MM-DD
    file_handler = logging.handlers.TimedRotatingFileHandler(
        filename=logs_dir / "app.log",
        when="midnight",
        backupCount=30,
        encoding="utf-8",
    )
    file_handler.suffix = "%Y-%m-%d"
    file_handler.setFormatter(fmt)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(fmt)

    root = logging.getLogger()
    root.setLevel(level)
    root.addHandler(file_handler)
    root.addHandler(console_handler)


_configure_logging()
logger = logging.getLogger(__name__)


async def _timeout_sweep_loop() -> None:
    """Periodically sweep stuck 'ending' sessions every 30 seconds."""
    manager = SessionManager()
    while True:
        try:
            timed_out = await manager.timeout_sweep()
            if timed_out:
                logger.info("Timeout sweep: transitioned %d stuck sessions to ended", timed_out)
        except Exception:
            logger.exception("Error during timeout sweep")
        await asyncio.sleep(30)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage MongoDB connection lifecycle and background tasks."""
    await connect_db()
    sweep_task = asyncio.create_task(_timeout_sweep_loop())
    yield
    sweep_task.cancel()
    try:
        await sweep_task
    except asyncio.CancelledError:
        pass
    await disconnect_db()


app = FastAPI(title="MentorMan Unified Backend", lifespan=lifespan)

# CORS — allow the dev SPA origin (production is same-origin, served by FastAPI).
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

# Register routers
app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(profile.router)
app.include_router(skills.router)
app.include_router(sessions.router)
app.include_router(session_upload.router)
app.include_router(mentor.router)
app.include_router(onboarding.router)
app.include_router(ingest.router)
app.include_router(memory.router)
app.include_router(topics.router)


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok"}


# ─── Serve the built React SPA (same-origin production) ────────────────────────
# Mounts the Vite build (mentorman-web/dist) as static assets and serves
# index.html as the SPA fallback for unmatched non-API GET paths. API routers and
# /health are registered above, so they take precedence over this fallback.
_default_spa = Path(__file__).resolve().parents[2] / "mentorman-web" / "dist"
SPA_DIST_DIR = Path(os.environ.get("SPA_DIST_DIR", str(_default_spa)))

if SPA_DIST_DIR.is_dir():
    _assets = SPA_DIST_DIR / "assets"
    if _assets.is_dir():
        app.mount("/assets", StaticFiles(directory=str(_assets)), name="assets")

    _index = SPA_DIST_DIR / "index.html"

    @app.get("/{full_path:path}")
    async def spa_fallback(full_path: str):
        """Serve a static file if it exists, else index.html for client routing."""
        candidate = SPA_DIST_DIR / full_path
        if full_path and candidate.is_file():
            return FileResponse(str(candidate))
        return FileResponse(str(_index))
