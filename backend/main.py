from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from core.config import settings
from api.chat import router as chat_router
from api.ingestion import router as ingestion_router
from api.profile import router as profile_router

app = FastAPI(title="AI Mentor API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat_router)
app.include_router(ingestion_router)
app.include_router(profile_router)


@app.get("/health")
async def health():
    return {"status": "ok"}
