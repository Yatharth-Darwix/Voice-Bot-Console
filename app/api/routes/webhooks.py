"""Webhook ingestion routes."""

from fastapi import APIRouter

import call_router

router = APIRouter(prefix="/api")
public_router = APIRouter()

router.add_api_route(
    "/webhook/vapi",
    call_router.vapi_webhook,
    methods=["POST"],
)

public_router.add_api_route(
    "/webhook/vapi/server",
    call_router.vapi_server_webhook,
    methods=["POST"],
)
public_router.add_api_route(
    "/webhook/vapi/server/",
    call_router.vapi_server_webhook,
    methods=["POST"],
)
