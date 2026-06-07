"""MentorMan Unified Backend — FastAPI application entry point."""

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config.database import connect_db, disconnect_db
from app.config.settings import get_settings
from app.routers import (
    ingest,
    memory,
    mentor,
    onboarding,
    profile,
    session_end,
    session_upload,
    sessions,
    skills,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage MongoDB connection lifecycle."""
    await connect_db()
    yield
    await disconnect_db()


app = FastAPI(title="MentorMan Unified Backend", lifespan=lifespan)

# CORS — allow the dev SPA origin (production is same-origin, served by FastAPI).
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

# Register routers
app.include_router(profile.router)
app.include_router(skills.router)
app.include_router(sessions.router)
app.include_router(session_end.router)
app.include_router(session_upload.router)
app.include_router(mentor.router)
app.include_router(onboarding.router)
app.include_router(ingest.router)
app.include_router(memory.router)


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
