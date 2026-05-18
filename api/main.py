"""FastAPI application entrypoint."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from api.routes import config, status, trades
from config.logging_config import configure_logging
from config.settings import settings
from data.storage import redis_cache, timescale


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging(settings.log_level)
    yield
    await timescale.close_pool()
    await redis_cache.close_redis()


app = FastAPI(
    title="PulsarAI",
    description="AI crypto trading bot control API",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(status.router, prefix="/api/v1", tags=["status"])
app.include_router(trades.router, prefix="/api/v1", tags=["trades"])
app.include_router(config.router, prefix="/api/v1", tags=["config"])


@app.get("/")
async def root() -> dict[str, str]:
    return {"service": "PulsarAI API", "docs": "/docs"}
