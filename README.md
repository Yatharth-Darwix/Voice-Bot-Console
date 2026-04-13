# VoiceForge Demo Voice Bot

FastAPI backend that:
- Streams dynamic voice-agent prompt generation from OpenAI Realtime API.
- Starts outbound calls through Vapi using generated `systemPrompt` and `firstMessage`.
- Prepares dynamic in-browser bot sessions for direct voice interaction in dashboard.

## 1) Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Fill `.env`:
- `OPENAI_API_KEY`
- `VAPI_API_KEY`
- `VAPI_PHONE_NUMBER_ID`
- `VAPI_ASSISTANT_ID`
- `VAPI_SERVER_PUBLIC_BASE_URL` (optional, e.g. `https://xxxx.ngrok-free.app`)
- `ELEVENLABS_VOICE_ID`
- `WEB_SEARCH_PROVIDER` (`tavily`)
- `WEB_SEARCH_API_KEY`

## 2) Run

```bash
source .venv/bin/activate
uvicorn app.main:app --reload --port 8557
```

Backward-compatible entrypoint still works:

```bash
uvicorn main:app --reload --port 8557
```

Health check:

```bash
curl http://localhost:8557/health
```

## 3) Trigger a Call

```bash
curl -N -X POST http://localhost:8557/api/initiate-call \
  -H "Content-Type: application/json" \
  -d '{
    "industry": "SaaS",
    "company": "Acme AI",
    "use_case": "Book a product demo",
    "persona": "Warm, concise, confident sales rep",
    "guardrails": "Do not claim discounts or contracts. Stop if asked.",
    "phone_number": "+14155550123"
  }'
```

The endpoint returns `text/event-stream` events for:
- prompt token streaming
- greeting generation status
- final Vapi call initiation result (`call_id`)

## 4) Prepare Browser Bot Session

```bash
curl -X POST http://localhost:8557/api/prepare-browser-bot \
  -H "Content-Type: application/json" \
  -d '{
    "industry": "SaaS",
    "company": "Acme AI",
    "use_case": "Book a product demo",
    "persona": "Warm, concise, confident sales rep",
    "guardrails": "Do not claim discounts or contracts. Stop if asked."
  }'
```

Returns:
- `system_prompt`
- `first_message`
- `assistant_id`
- `assistant_overrides`

## 5) Frontend

```bash
cd frontend
npm install
cp .env.example .env
npm run dev
```

Default frontend URL: `http://localhost:5173`  
Default backend proxy target: `http://127.0.0.1:8557`

Dashboard modes:
- `Phone Call`: Existing flow, generates prompt and dials target phone number.
- `Talk In Browser`: New flow, generates prompt and starts a browser voice session via Vapi Web SDK.

Prompt generation now enforces bilingual handling (English/Hindi) with automatic language switching when the customer switches.
Phone mode dashboard now also shows live transcript messages when webhook sync is active.

For browser mode, set `VITE_VAPI_PUBLIC_KEY` in `frontend/.env`.
For production browser voice, run over HTTPS to ensure microphone permissions work reliably.

## 6) Session Logs Dashboard

- Open `/sessions` in the frontend to monitor sessions.
- Each run creates a `session_id`.
- Logs page shows:
  - mode (`phone` / `browser`)
  - status
  - `call_id` (once available)
  - transcript/messages per session (from webhook and/or Vapi call fetch)

## 7) Vapi Server Webhook + ngrok

Use this when you want Vapi to send transcript/status/tool-calls into your local backend.

1. Run backend:

```bash
uvicorn main:app --reload --port 8557
```

2. Expose backend with ngrok:

```bash
ngrok http 8557
```

3. In Vapi assistant/server settings:
- `server.url` -> `https://<your-ngrok-id>.ngrok-free.app/webhook/vapi/server`
- Include `serverMessages` at least:
  - `status-update`
  - `transcript[transcriptType="final"]`
  - `speech-update`
  - `end-of-call-report`
  - `tool-calls`

4. Trigger a call and open `/sessions` in frontend to inspect logs/transcript.

Optional automation from dashboard:
- In `Pipeline Status` use **Sync Vapi Webhook**.
- Leave URL empty to auto-detect from local ngrok API (`http://127.0.0.1:4040/api/tunnels`),
  or paste your ngrok base URL manually.
- Backend endpoint used: `POST /api/vapi/configure-webhook`.

Permanent ngrok URL from `.env`:
- Set `VAPI_SERVER_PUBLIC_BASE_URL=https://<your-ngrok-id>.ngrok-free.app`
- Then webhook sync uses this value by default (no need to paste each time).
- Phone/browser flows also attempt auto-sync from this env value before starting.

## 8) Live web_search tool

Server route processes Vapi `tool-calls` events and supports tool name `web_search`.

- Tool endpoint: same assistant `server.url` (`/webhook/vapi/server`)
- Expected arguments:
  - `query` (string)
  - optional `max_results` (number)
- Response is returned in Vapi `results` format (`toolCallId`, `result`/`error`).

## 9) Developer quality checks

Install dev tooling:

```bash
pip install -r requirements-dev.txt
```

Run checks:

```bash
ruff check .
black --check .
mypy .
pytest
```

## 10) Architecture and backlog snapshot

See `docs/ARCHITECTURE_BACKLOG.md` for the current module map and next recommended implementation backlog.
