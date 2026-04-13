# Architecture & Backlog Snapshot

This document summarizes the current backend structure after the refactor phases and lists the highest-value next items.

## Current Backend Layout

- `app/main.py`: FastAPI app assembly (middleware + router composition).
- `app/api/routes/`: Route registration split by domain:
  - `calls.py`
  - `sessions.py`
  - `webhooks.py`
- `app/schemas/call_models.py`: Request/response contracts and validators.
- `app/services/`: Business workflows:
  - `call_service.py` (prompt/call pipeline orchestration)
  - `session_service.py` (session summary + Vapi message merge/cache)
  - `webhook_service.py` (webhook event orchestration)
  - `webhook_state_service.py` (session state mutation helpers)
  - `webhook_config_service.py` (ngrok discovery + webhook configuration)
- `app/utils/`:
  - `message_normalizers.py`
  - `router_helpers.py`

## Runtime Entry Points

- Preferred backend entrypoint: `uvicorn app.main:app --reload --port 8557`
- Compatibility entrypoint remains available: `uvicorn main:app --reload --port 8557`

## Immediate Backlog (Recommended)

1. Add integration tests for:
   - `POST /api/initiate-call` stream phases
   - `POST /api/webhook/vapi` state transitions
   - `GET /api/sessions/{session_id}` merge behavior
2. Replace in-memory stores with production-safe components:
   - session store (Redis/Postgres)
   - distributed rate limiting (Redis)
3. Introduce auth/authorization for operational routes.
4. Add structured request IDs and metrics for pipeline/webhook observability.
5. Add CI workflow gates for:
   - `ruff check .`
   - `pytest`
   - optional `mypy`

## Definition of Done for Refactor Track

- Thin route handlers, centralized schemas, service-isolated business logic.
- Stable behavior across phone flow, browser flow, session logs, and webhooks.
- Baseline lint/test checks passing consistently.
