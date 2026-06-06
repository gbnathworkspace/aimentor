"""Main FastAPI application entry point for the Ingestion Pipeline."""

from fastapi import FastAPI

from app.routers.ingest import router as ingest_router
from app.routers.session import router as session_router

app = FastAPI(
    title="MentorMan Ingestion Pipeline",
    description="Backend service for data ingestion: PDF/CSV upload processing, "
    "session-end processing, and embedding storage.",
    version="0.1.0",
)

app.include_router(ingest_router)
app.include_router(session_router)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok"}
