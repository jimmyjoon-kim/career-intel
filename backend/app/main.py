import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .db import init_db
from .routers import agents, ask, auth, market, matches, profile, scorecard

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


_docs = get_settings().enable_docs
app = FastAPI(title="Career Intel API", version="0.1.0", lifespan=lifespan,
              docs_url="/docs" if _docs else None, redoc_url=None, openapi_url="/openapi.json" if _docs else None)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in get_settings().cors_origins.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
for r in (auth.router, profile.router, market.router, ask.router, scorecard.router, matches.router, agents.router):
    app.include_router(r)


@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/api/version")
def app_version():
    from .agents.health import version

    return {"commit": version()}


@app.get("/api/health/status")
def health_status(days: int = 7):
    """Numbers only: the latest result of each daily check. Read by the weekly audit; holds no personal data."""
    from .agents.health import status
    from .db import SessionLocal

    with SessionLocal() as db:
        return status(db, max(1, min(days, 31)))
