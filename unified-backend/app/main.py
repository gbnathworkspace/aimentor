"""MentorMan Unified Backend — FastAPI application entry point."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config.database import connect_db, disconnect_db
from app.routers import (
    ingest,
    memory,
    mentor,
    onboarding,
    profile,
    session_end,
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

# Register routers
app.include_router(profile.router)
app.include_router(skills.router)
app.include_router(sessions.router)
app.include_router(session_end.router)
app.include_router(mentor.router)
app.include_router(onboarding.router)
app.include_router(ingest.router)
app.include_router(memory.router)


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok"}
