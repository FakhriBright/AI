from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import auth, health
from app.core.config import settings

app = FastAPI(
    title="AI Trading Analysis Platform",
    description=(
        "Decision-support analysis API. Not an auto-trading system — "
        "execution stays manual via MT5."
    ),
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(auth.router)

# Technical / fundamental / risk / AI analysis routers are added in their
# owning phases (3-7) — deliberately not stubbed here yet.
