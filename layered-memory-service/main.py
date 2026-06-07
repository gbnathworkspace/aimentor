import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.dal import mongo
from app.api.routes import l1_profile, l2_skill, l3_episodic, chat, session, onboarding

logging.basicConfig(level=settings.log_level.upper())
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    mongo.connect()
    yield
    mongo.disconnect()


app = FastAPI(title="layered-memory-service", lifespan=lifespan)

app.include_router(l1_profile.router)
app.include_router(l2_skill.router)
app.include_router(l3_episodic.router)
app.include_router(chat.router)
app.include_router(session.router)
app.include_router(onboarding.router)


@app.get("/health", tags=["Health"])
def health():
    return JSONResponse({"status": "ok"})
