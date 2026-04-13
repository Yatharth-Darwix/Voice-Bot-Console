"""Route modules entrypoint."""

from fastapi import APIRouter

from app.api.routes import calls, sessions, webhooks

router = APIRouter()
router.include_router(calls.router)
router.include_router(sessions.router)
router.include_router(webhooks.router)

public_router = APIRouter()
public_router.include_router(webhooks.public_router)

__all__ = ["router", "public_router"]
