"""Call initiation and bot preparation routes."""

from fastapi import APIRouter

import call_router

router = APIRouter(prefix="/api")

router.add_api_route(
    "/initiate-call",
    call_router.initiate_call,
    methods=["POST"],
)

router.add_api_route(
    "/prepare-browser-bot",
    call_router.prepare_browser_bot,
    methods=["POST"],
    response_model=call_router.PrepareBrowserBotResponse,
)

router.add_api_route(
    "/vapi/configure-webhook",
    call_router.configure_vapi_webhook,
    methods=["POST"],
    response_model=call_router.ConfigureWebhookResponse,
)
