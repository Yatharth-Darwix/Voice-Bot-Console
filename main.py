"""
VoiceForge — FastAPI Application Entry Point
Run: uvicorn main:app --reload --port 8557
"""

import logging
import sys

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from call_router import public_router, router as call_router

# ── Logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

# ── App ────────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="VoiceForge AI Voice Agent API",
    description="Generates system prompts via GPT-4o WebSocket and fires Vapi outbound calls.",
    version="1.0.0",
    docs_url="/docs" if settings.app_env == "development" else None,
)

# ── CORS ───────────────────────────────────────────────────────────────────────
allowed_origins = {settings.frontend_origin}
if "localhost" in settings.frontend_origin:
    allowed_origins.add(settings.frontend_origin.replace("localhost", "127.0.0.1"))
if "127.0.0.1" in settings.frontend_origin:
    allowed_origins.add(settings.frontend_origin.replace("127.0.0.1", "localhost"))

app.add_middleware(
    CORSMiddleware,
    allow_origins=sorted(allowed_origins),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ────────────────────────────────────────────────────────────────────
app.include_router(call_router)
app.include_router(public_router)


@app.get("/health")
async def health():
    return {"status": "ok", "env": settings.app_env}


logger.info("VoiceForge API starting — env=%s", settings.app_env)
