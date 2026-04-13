"""Session query and mutation routes."""

from fastapi import APIRouter

import call_router

router = APIRouter(prefix="/api")

router.add_api_route(
    "/sessions",
    call_router.list_sessions,
    methods=["GET"],
    response_model=call_router.SessionListResponse,
)

router.add_api_route(
    "/sessions/{session_id}",
    call_router.get_session,
    methods=["GET"],
    response_model=call_router.SessionDetailResponse,
)

router.add_api_route(
    "/sessions/{session_id}/bind-call",
    call_router.bind_session_call,
    methods=["POST"],
)

router.add_api_route(
    "/sessions/{session_id}/events",
    call_router.append_session_event,
    methods=["POST"],
)
