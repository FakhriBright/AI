import logging
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import analysis, auth, health, market
from app.core.config import settings

logger = logging.getLogger("app_error")

app = FastAPI(
    title="AI Trading Analysis Platform",
    description=(
        "Decision-support analysis API. Not an auto-trading system — "
        "execution stays manual via MT5."
    ),
    version="0.1.0",
)

# Tightened CORS configuration: explicit origins only, no loose regex
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Sanitize internal exceptions: log technical tracebacks on server, return clean 500 error to client
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled server error processing %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "An internal error occurred. Please try again later."},
    )

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(market.router)
app.include_router(analysis.router)
